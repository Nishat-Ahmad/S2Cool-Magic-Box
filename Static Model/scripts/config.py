"""Configuration and CLI argument parsing for train_xgboost."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

CITY_COORDS: dict[str, tuple[float, float]] = {
    "Islamabad": (33.6844, 73.0479),
    "Lahore": (31.5204, 74.3587),
    "Karachi": (24.8607, 67.0011),
    "Peshawar": (34.0151, 71.5249),
}


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


def parse_iso_date(date_str: str, label: str) -> date:
    """Parse YYYY-MM-DD string into date with clear error message."""
    try:
        return date.fromisoformat(date_str)
    except ValueError as exc:
        raise ValueError(f"Invalid {label}: {date_str}. Expected YYYY-MM-DD") from exc
