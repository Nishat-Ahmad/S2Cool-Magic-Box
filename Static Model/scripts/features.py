"""Feature engineering for train_xgboost."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("static_xgboost")


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
