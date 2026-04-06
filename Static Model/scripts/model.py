"""Model training and evaluation utilities for train_xgboost."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

LOGGER = logging.getLogger("static_xgboost")


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
