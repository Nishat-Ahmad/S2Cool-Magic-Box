"""Train an XGBoost model from Excel files in Static Model/Dataset.

This script builds a next-hour GHI regressor using chronological features,
lagged weather context, and rolling-window statistics.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

LOGGER = logging.getLogger("static_xgboost")


def configure_logging() -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Train next-hour GHI XGBoost model.")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "Dataset",
        help="Folder containing .xlsx files.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts",
        help="Output folder for model/metrics.",
    )
    parser.add_argument(
        "--max-rows-per-file",
        type=int,
        default=20000,
        help="Maximum rows to read from each Excel file (0 means full file).",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="Maximum number of files to process (0 means all files).",
    )
    parser.add_argument(
        "--target-mode",
        choices=["ghi", "temperature", "both"],
        default="ghi",
        help="Training target: next-hour GHI, next-hour temperature, or both.",
    )
    parser.add_argument(
        "--backtest-mode",
        choices=["holdout", "rolling"],
        default="holdout",
        help="Evaluation mode: single holdout split or rolling-window backtest.",
    )
    parser.add_argument(
        "--rolling-train-size",
        type=int,
        default=0,
        help="Rolling backtest train window size (0 = auto).",
    )
    parser.add_argument(
        "--rolling-test-size",
        type=int,
        default=0,
        help="Rolling backtest test window size (0 = auto).",
    )
    parser.add_argument(
        "--rolling-step-size",
        type=int,
        default=0,
        help="Rolling backtest step size (0 = same as test size).",
    )
    parser.add_argument(
        "--rolling-max-folds",
        type=int,
        default=5,
        help="Maximum rolling folds to evaluate.",
    )
    parser.add_argument(
        "--test-year",
        type=int,
        default=2026,
        help="Calendar year used as holdout test set in holdout mode.",
    )
    parser.add_argument(
        "--test-dataset-dir",
        type=Path,
        default=None,
        help="Optional external dataset directory used only for testing (e.g., 2026 data).",
    )
    parser.add_argument(
        "--test-source",
        choices=["dataset", "api"],
        default="dataset",
        help="Where holdout test data should come from.",
    )
    parser.add_argument(
        "--api-city",
        choices=["Islamabad", "Lahore", "Karachi", "Peshawar"],
        default="Islamabad",
        help="City used when --test-source api.",
    )
    parser.add_argument(
        "--api-start-date",
        type=str,
        default=None,
        help="Start date YYYY-MM-DD for API test data (defaults to test-year-01-01).",
    )
    parser.add_argument(
        "--api-end-date",
        type=str,
        default=None,
        help="End date YYYY-MM-DD for API test data (defaults to UTC today - 2 days).",
    )
    return parser.parse_args()


CITY_COORDS: dict[str, tuple[float, float]] = {
    "Islamabad": (33.6844, 73.0479),
    "Lahore": (31.5204, 74.3587),
    "Karachi": (24.8607, 67.0011),
    "Peshawar": (34.0151, 71.5249),
}


def _parse_iso_date(date_str: str, label: str) -> date:
    """Parse YYYY-MM-DD string into date with clear error message."""
    try:
        return date.fromisoformat(date_str)
    except ValueError as exc:
        raise ValueError(f"Invalid {label}: {date_str}. Expected YYYY-MM-DD") from exc


def load_api_test_dataset(
    city: str,
    test_year: int,
    api_start_date: str | None,
    api_end_date: str | None,
) -> pd.DataFrame:
    """Load test set from Open-Meteo archive API in canonical schema."""
    lat, lon = CITY_COORDS[city]

    start_date = _parse_iso_date(api_start_date, "api-start-date") if api_start_date else date(test_year, 1, 1)
    end_date = _parse_iso_date(api_end_date, "api-end-date") if api_end_date else (datetime.now(UTC).date() - timedelta(days=2))
    if end_date < start_date:
        raise ValueError(f"api-end-date {end_date} is before api-start-date {start_date}.")

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": (
            "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,"
            "surface_pressure,shortwave_radiation,direct_radiation,diffuse_radiation"
        ),
        "timezone": "UTC",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    url = "https://archive-api.open-meteo.com/v1/archive"
    query = urllib.parse.urlencode(params)
    request_url = f"{url}?{query}"
    with urllib.request.urlopen(request_url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise RuntimeError("Open-Meteo response missing 'hourly' block.")

    times = hourly.get("time") or []
    if not times:
        raise RuntimeError("Open-Meteo response contains no hourly time rows.")

    size = len(times)

    def col(name: str) -> list[float | None]:
        values = hourly.get(name)
        if values is None:
            return [None] * size
        return values

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(times, errors="coerce", utc=True),
            "temperature": col("temperature_2m"),
            "humidity": col("relative_humidity_2m"),
            "wind_speed": col("wind_speed_10m"),
            "wind_gust": col("wind_gusts_10m"),
            "pressure": col("surface_pressure"),
            "ghi": col("shortwave_radiation"),
            "dni": col("direct_radiation"),
            "dhi": col("diffuse_radiation"),
            "source_file": f"api:{city}:{start_date}->{end_date}",
        }
    )
    df = df.dropna(subset=["timestamp", "ghi"]).reset_index(drop=True)
    LOGGER.info(
        "Loaded API test dataset for %s: rows=%d range=%s->%s",
        city,
        len(df),
        start_date,
        end_date,
    )
    return df


def _canonical_col_name(raw: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")
    aliases = {
        "temp": "temperature",
        "winddirection": "wind_direction",
        "windspeed": "wind_speed",
        "windgust": "wind_gust",
        "tair_avg": "temperature",
        "tamb": "temperature",
        "rh_avg": "humidity",
        "rh": "humidity",
        "bp_cs100_avg": "pressure",
        "bp": "pressure",
        "ghi_corr_avg": "ghi",
        "dni_corr_avg": "dni",
        "dhi_corr_avg": "dhi",
        "ws": "wind_speed",
        "wsgust": "wind_gust",
        "wd": "wind_direction",
        "timestamp": "timestamp",
        "ts": "timestamp",
        "ws_wvc_1": "wind_speed",
    }
    return aliases.get(normalized, normalized)


def _read_with_strategies(file_path: Path, nrows: int | None) -> pd.DataFrame | None:
    """Read a file using format-specific sheet/header strategies."""
    name_lower = file_path.name.lower()

    if name_lower.startswith("pk_isb_") or name_lower.startswith("pk-isb_"):
        strategies: list[tuple[str | int, int]] = [
            ("1h", 18),
            ("10min", 18),
            ("day", 18),
            (0, 0),
        ]
    else:
        strategies = [
            (0, 0),
            ("Sheet1", 0),
            ("data", 0),
            ("1h", 18),
        ]

    for sheet_name, header_row in strategies:
        try:
            return pd.read_excel(file_path, sheet_name=sheet_name, header=header_row, nrows=nrows)
        except Exception:
            continue
    return None


def _standardize_frame(df: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """Normalize columns and produce canonical weather frame."""
    work = df.copy()
    work.columns = [_canonical_col_name(str(col)) for col in work.columns]

    if "timestamp" in work.columns:
        work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce", utc=True)
    elif "date" in work.columns and "time" in work.columns:
        work["timestamp"] = pd.to_datetime(
            work["date"].astype(str) + " " + work["time"].astype(str),
            errors="coerce",
            utc=True,
        )
    elif "date" in work.columns:
        work["timestamp"] = pd.to_datetime(work["date"], errors="coerce", utc=True)
    else:
        return pd.DataFrame()

    numeric_cols = [
        "temperature",
        "humidity",
        "wind_direction",
        "wind_speed",
        "wind_gust",
        "pressure",
        "ghi",
        "dni",
        "dhi",
    ]
    present_numeric = [col for col in numeric_cols if col in work.columns]
    for col in present_numeric:
        work[col] = pd.to_numeric(work[col], errors="coerce")

    if "ghi" not in work.columns:
        return pd.DataFrame()

    keep_cols = ["timestamp", *present_numeric]
    out = work[keep_cols].copy()
    out = out.dropna(subset=["timestamp", "ghi"])
    out["source_file"] = file_name
    return out


def load_dataset(dataset_dir: Path, max_rows_per_file: int, max_files: int) -> pd.DataFrame:
    """Load and unify all Excel files from the dataset folder."""
    files = sorted(dataset_dir.glob("*.xlsx"))
    if max_files > 0:
        files = files[:max_files]

    if not files:
        raise FileNotFoundError(f"No .xlsx files found in {dataset_dir}")

    frames: list[pd.DataFrame] = []
    for idx, file_path in enumerate(files, start=1):
        LOGGER.info("Reading file %d/%d: %s", idx, len(files), file_path.name)
        nrows = max_rows_per_file if max_rows_per_file > 0 else None

        try:
            if not zipfile.is_zipfile(file_path):
                raise ValueError("File is not a zip file")
            df = _read_with_strategies(file_path, nrows=nrows)
            if df is None:
                LOGGER.warning("Skipping %s (no readable sheet/header strategy)", file_path.name)
                continue
        except Exception as exc:
            LOGGER.warning("Skipping %s (read failed: %s)", file_path.name, exc)
            continue

        if df.empty:
            continue

        standardized = _standardize_frame(df, file_path.name)
        if standardized.empty:
            LOGGER.warning("Skipping %s (required columns missing)", file_path.name)
            continue

        frames.append(standardized)

    if not frames:
        raise RuntimeError("No usable files found after schema normalization.")

    merged = pd.concat(frames, ignore_index=True)
    LOGGER.info(
        "Loaded %d rows from %d files (max_rows_per_file=%d)",
        len(merged),
        len(frames),
        max_rows_per_file,
    )
    return merged


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Build a model-ready frame with engineered features and both targets."""
    work = df.copy()
    if "timestamp" not in work.columns:
        raise KeyError("Expected canonical 'timestamp' column after loading data.")

    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce", utc=True)
    work = work.dropna(subset=["timestamp"]).sort_values("timestamp")

    numeric_cols = [
        "temperature",
        "humidity",
        "wind_direction",
        "wind_speed",
        "wind_gust",
        "pressure",
        "ghi",
        "dni",
        "dhi",
    ]
    for col in numeric_cols:
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")

    present_numeric = [col for col in numeric_cols if col in work.columns]
    work = work.dropna(subset=["ghi"])
    work[present_numeric] = work[present_numeric].interpolate(limit_direction="both")
    work[present_numeric] = work[present_numeric].ffill().bfill()

    # Consolidate duplicate timestamps by averaging numeric weather columns.
    grouped = work.groupby("timestamp", as_index=False)[present_numeric].mean()
    grouped = grouped.sort_values("timestamp").reset_index(drop=True)

    ts = grouped["timestamp"]
    grouped["hour"] = ts.dt.hour
    grouped["day_of_year"] = ts.dt.dayofyear
    grouped["month"] = ts.dt.month

    grouped["hour_sin"] = np.sin(2 * np.pi * grouped["hour"] / 24)
    grouped["hour_cos"] = np.cos(2 * np.pi * grouped["hour"] / 24)
    grouped["doy_sin"] = np.sin(2 * np.pi * grouped["day_of_year"] / 365.25)
    grouped["doy_cos"] = np.cos(2 * np.pi * grouped["day_of_year"] / 365.25)

    for lag in (1, 2, 3, 24):
        grouped[f"ghi_lag_{lag}"] = grouped["ghi"].shift(lag)

    if "temperature" in grouped.columns:
        grouped["temp_lag_1"] = grouped["temperature"].shift(1)

    grouped["ghi_rolling_mean_3h"] = grouped["ghi"].shift(1).rolling(3, min_periods=1).mean()
    grouped["ghi_rolling_std_3h"] = grouped["ghi"].shift(1).rolling(3, min_periods=2).std()
    grouped["target_ghi_next_1h"] = grouped["ghi"].shift(-1)
    grouped["target_temperature_next_1h"] = grouped["temperature"].shift(-1)

    grouped = grouped.dropna(subset=["target_ghi_next_1h", "target_temperature_next_1h"]).copy()
    return grouped.fillna(0.0)


def prepare_features(df: pd.DataFrame, target_mode: str) -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    """Build feature matrix and selected target vector."""
    grouped = build_feature_frame(df)

    target_column = {
        "ghi": "target_ghi_next_1h",
        "temperature": "target_temperature_next_1h",
    }[target_mode]

    feature_cols = [
        col
        for col in grouped.columns
        if col
        not in {
            "timestamp",
            "target_ghi_next_1h",
            "target_temperature_next_1h",
        }
    ]
    x = grouped[feature_cols]
    y = grouped[target_column]
    ts = grouped["timestamp"]

    LOGGER.info("Prepared features for %s: rows=%d cols=%d", target_mode, x.shape[0], x.shape[1])
    return x, y, ts, target_column


def train_and_evaluate(
    x: pd.DataFrame,
    y: pd.Series,
    timestamps: pd.Series,
    test_year: int,
) -> tuple[XGBRegressor, dict[str, float], pd.DataFrame]:
    """Train using pre-test-year rows and evaluate on rows in ``test_year``."""
    years = pd.to_datetime(timestamps, errors="coerce", utc=True).dt.year
    test_mask = years == test_year
    train_mask = years < test_year

    if int(test_mask.sum()) == 0:
        raise ValueError(f"No rows found for test_year={test_year}.")
    if int(train_mask.sum()) == 0:
        raise ValueError(f"No train rows found before test_year={test_year}.")

    x_train, x_test = x.loc[train_mask], x.loc[test_mask]
    y_train, y_test = y.loc[train_mask], y.loc[test_mask]

    model = XGBRegressor(
        objective="reg:squarederror",
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)

    pred_test = model.predict(x_test)
    metrics = {
        "train_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
        "test_year": int(test_year),
        "mae": float(mean_absolute_error(y_test, pred_test)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, pred_test))),
        "r2": float(r2_score(y_test, pred_test)),
    }

    pred_df = pd.DataFrame(
        {
            "actual": y_test.to_numpy(),
            "predicted": pred_test,
            "residual": y_test.to_numpy() - pred_test,
        }
    )
    return model, metrics, pred_df


def train_and_evaluate_explicit_split(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    test_descriptor: str,
) -> tuple[XGBRegressor, dict[str, float], pd.DataFrame]:
    """Train on explicit train split and evaluate on explicit test split."""
    model = XGBRegressor(
        objective="reg:squarederror",
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)

    pred_test = model.predict(x_test)
    metrics = {
        "train_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
        "test_descriptor": test_descriptor,
        "mae": float(mean_absolute_error(y_test, pred_test)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, pred_test))),
        "r2": float(r2_score(y_test, pred_test)),
    }

    pred_df = pd.DataFrame(
        {
            "actual": y_test.to_numpy(),
            "predicted": pred_test,
            "residual": y_test.to_numpy() - pred_test,
        }
    )
    return model, metrics, pred_df


def rolling_backtest(
    x: pd.DataFrame,
    y: pd.Series,
    train_size: int,
    test_size: int,
    step_size: int,
    max_folds: int,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Run fixed-window rolling backtest and return fold metrics + summary."""
    total_rows = len(x)
    if total_rows < train_size + test_size:
        raise ValueError(
            f"Not enough rows for rolling backtest: rows={total_rows}, "
            f"train_size={train_size}, test_size={test_size}."
        )

    rows: list[dict[str, float | int]] = []
    fold = 0
    train_start = 0

    while fold < max_folds:
        train_end = train_start + train_size
        test_end = train_end + test_size
        if test_end > total_rows:
            break

        x_train = x.iloc[train_start:train_end]
        y_train = y.iloc[train_start:train_end]
        x_test = x.iloc[train_end:test_end]
        y_test = y.iloc[train_end:test_end]

        model = XGBRegressor(
            objective="reg:squarederror",
            n_estimators=500,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(x_train, y_train)
        preds = model.predict(x_test)

        rows.append(
            {
                "fold": fold + 1,
                "train_start": int(train_start),
                "train_end": int(train_end - 1),
                "test_start": int(train_end),
                "test_end": int(test_end - 1),
                "train_rows": int(len(x_train)),
                "test_rows": int(len(x_test)),
                "mae": float(mean_absolute_error(y_test, preds)),
                "rmse": float(np.sqrt(mean_squared_error(y_test, preds))),
                "r2": float(r2_score(y_test, preds)),
            }
        )

        fold += 1
        train_start += step_size

    if not rows:
        raise RuntimeError("Rolling backtest produced no folds.")

    folds_df = pd.DataFrame(rows)
    summary = {
        "folds": int(len(folds_df)),
        "train_size": int(train_size),
        "test_size": int(test_size),
        "step_size": int(step_size),
        "mae_mean": float(folds_df["mae"].mean()),
        "mae_std": float(folds_df["mae"].std(ddof=0)),
        "rmse_mean": float(folds_df["rmse"].mean()),
        "rmse_std": float(folds_df["rmse"].std(ddof=0)),
        "r2_mean": float(folds_df["r2"].mean()),
        "r2_std": float(folds_df["r2"].std(ddof=0)),
    }
    return folds_df, summary


def save_artifacts(
    model: XGBRegressor,
    metrics: dict[str, float],
    pred_df: pd.DataFrame,
    x_columns: list[str],
    artifacts_dir: Path,
    target_mode: str,
) -> None:
    """Save model, metrics, feature importance, and holdout predictions."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    suffix = "ghi" if target_mode == "ghi" else "temp"

    model_path = artifacts_dir / f"xgboost_{suffix}_model.joblib"
    metrics_path = artifacts_dir / f"xgboost_{suffix}_metrics.json"
    predictions_path = artifacts_dir / f"xgboost_{suffix}_test_predictions.csv"
    feature_importance_path = artifacts_dir / f"xgboost_{suffix}_feature_importance.csv"

    joblib.dump(model, model_path)

    payload = {
        "model_name": f"xgboost_{target_mode}_next_1h",
        "target_mode": target_mode,
        "feature_count": len(x_columns),
        "features": x_columns,
        **metrics,
    }
    metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    pred_df.to_csv(predictions_path, index=False)

    importance = pd.DataFrame(
        {
            "feature": x_columns,
            "importance": model.feature_importances_,
        }
    ).sort_values("importance", ascending=False)
    importance.to_csv(feature_importance_path, index=False)

    LOGGER.info("Saved model: %s", model_path)
    LOGGER.info("Saved metrics: %s", metrics_path)
    LOGGER.info("Saved predictions: %s", predictions_path)
    LOGGER.info("Saved feature importance: %s", feature_importance_path)


def save_rolling_backtest_artifacts(
    folds_df: pd.DataFrame,
    summary: dict[str, float],
    artifacts_dir: Path,
    target_mode: str,
) -> None:
    """Save rolling backtest fold metrics and summary."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    suffix = "ghi" if target_mode == "ghi" else "temp"
    folds_path = artifacts_dir / f"xgboost_{suffix}_rolling_backtest_folds.csv"
    summary_path = artifacts_dir / f"xgboost_{suffix}_rolling_backtest_summary.json"

    folds_df.to_csv(folds_path, index=False)
    summary_payload = {
        "model_name": f"xgboost_{target_mode}_next_1h",
        "target_mode": target_mode,
        **summary,
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    LOGGER.info("Saved rolling folds: %s", folds_path)
    LOGGER.info("Saved rolling summary: %s", summary_path)


def main() -> None:
    """Run full training pipeline over the static Excel dataset."""
    configure_logging()
    args = parse_args()

    df = load_dataset(
        args.dataset_dir,
        max_rows_per_file=args.max_rows_per_file,
        max_files=args.max_files,
    )

    test_df: pd.DataFrame | None = None
    if args.backtest_mode == "holdout":
        if args.test_source == "api":
            test_df = load_api_test_dataset(
                city=args.api_city,
                test_year=args.test_year,
                api_start_date=args.api_start_date,
                api_end_date=args.api_end_date,
            )
        elif args.test_dataset_dir is not None:
            LOGGER.info("Loading external test dataset: %s", args.test_dataset_dir)
            test_df = load_dataset(
                args.test_dataset_dir,
                max_rows_per_file=args.max_rows_per_file,
                max_files=args.max_files,
            )

    modes = ["ghi", "temperature"] if args.target_mode == "both" else [args.target_mode]
    for mode in modes:
        x, y, ts, _ = prepare_features(df, mode)
        if args.backtest_mode == "holdout":
            if test_df is not None:
                x_test_raw, y_test, _, _ = prepare_features(test_df, mode)

                # Align columns so train/test matrices are strictly compatible.
                missing_in_test = [c for c in x.columns if c not in x_test_raw.columns]
                for col in missing_in_test:
                    x_test_raw[col] = 0.0
                extra_in_test = [c for c in x_test_raw.columns if c not in x.columns]
                if extra_in_test:
                    x_test_raw = x_test_raw.drop(columns=extra_in_test)
                x_test = x_test_raw[x.columns]

                if args.test_source == "api":
                    test_descriptor = (
                        f"api:{args.api_city}:{args.api_start_date or args.test_year}"
                        f"->{args.api_end_date or args.test_year}"
                    )
                else:
                    test_descriptor = f"external_dataset:{args.test_dataset_dir}"

                model, metrics, pred_df = train_and_evaluate_explicit_split(
                    x_train=x,
                    y_train=y,
                    x_test=x_test,
                    y_test=y_test,
                    test_descriptor=test_descriptor,
                )
            else:
                model, metrics, pred_df = train_and_evaluate(
                    x=x,
                    y=y,
                    timestamps=ts,
                    test_year=args.test_year,
                )
            save_artifacts(
                model,
                metrics,
                pred_df,
                list(x.columns),
                args.artifacts_dir,
                target_mode=mode,
            )
            LOGGER.info(
                "Training complete (%s) | MAE=%.4f RMSE=%.4f R2=%.4f",
                mode,
                metrics["mae"],
                metrics["rmse"],
                metrics["r2"],
            )
            continue

        total_rows = len(x)
        train_size = args.rolling_train_size if args.rolling_train_size > 0 else int(total_rows * 0.6)
        test_size = args.rolling_test_size if args.rolling_test_size > 0 else max(int(total_rows * 0.1), 500)
        step_size = args.rolling_step_size if args.rolling_step_size > 0 else test_size

        folds_df, summary = rolling_backtest(
            x=x,
            y=y,
            train_size=train_size,
            test_size=test_size,
            step_size=step_size,
            max_folds=args.rolling_max_folds,
        )
        save_rolling_backtest_artifacts(
            folds_df=folds_df,
            summary=summary,
            artifacts_dir=args.artifacts_dir,
            target_mode=mode,
        )
        LOGGER.info(
            "Rolling backtest complete (%s) | folds=%d MAE=%.4f±%.4f RMSE=%.4f±%.4f R2=%.4f±%.4f",
            mode,
            summary["folds"],
            summary["mae_mean"],
            summary["mae_std"],
            summary["rmse_mean"],
            summary["rmse_std"],
            summary["r2_mean"],
            summary["r2_std"],
        )


if __name__ == "__main__":
    main()
