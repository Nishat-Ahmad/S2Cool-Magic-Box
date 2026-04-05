"""Train an XGBoost model from Excel files in Static Model/Dataset.

This script builds a next-hour GHI regressor using chronological features,
lagged weather context, and rolling-window statistics.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import zipfile
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
    return parser.parse_args()


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


def prepare_features(df: pd.DataFrame, target_mode: str) -> tuple[pd.DataFrame, pd.Series, str]:
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

    LOGGER.info("Prepared features for %s: rows=%d cols=%d", target_mode, x.shape[0], x.shape[1])
    return x, y, target_column


def train_and_evaluate(x: pd.DataFrame, y: pd.Series) -> tuple[XGBRegressor, dict[str, float], pd.DataFrame]:
    """Train chronological split model and return metrics + predictions."""
    split_idx = int(len(x) * 0.8)
    x_train, x_test = x.iloc[:split_idx], x.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

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


def main() -> None:
    """Run full training pipeline over the static Excel dataset."""
    configure_logging()
    args = parse_args()

    df = load_dataset(
        args.dataset_dir,
        max_rows_per_file=args.max_rows_per_file,
        max_files=args.max_files,
    )
    modes = ["ghi", "temperature"] if args.target_mode == "both" else [args.target_mode]
    for mode in modes:
        x, y, _ = prepare_features(df, mode)
        model, metrics, pred_df = train_and_evaluate(x, y)
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


if __name__ == "__main__":
    main()
