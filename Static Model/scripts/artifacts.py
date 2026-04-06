"""Artifact saving utilities for train_xgboost."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import pandas as pd
from xgboost import XGBRegressor

LOGGER = logging.getLogger("static_xgboost")


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
