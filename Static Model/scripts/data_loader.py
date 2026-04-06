"""Data loading utilities for train_xgboost: Excel files and API-based datasets."""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from config import CITY_COORDS, parse_iso_date

LOGGER = logging.getLogger("static_xgboost")


def load_api_test_dataset(
    city: str,
    test_year: int,
    api_start_date: str | None,
    api_end_date: str | None,
) -> pd.DataFrame:
    """Load test set from Open-Meteo archive API in canonical schema."""
    lat, lon = CITY_COORDS[city]

    start_date = parse_iso_date(api_start_date, "api-start-date") if api_start_date else date(test_year, 1, 1)
    end_date = parse_iso_date(api_end_date, "api-end-date") if api_end_date else (datetime.now(UTC).date() - timedelta(days=2))
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
    """Normalize column name and apply known aliases."""
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
