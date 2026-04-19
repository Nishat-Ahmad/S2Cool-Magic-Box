"""Public file utilities for on-demand dataset fetching (no credentials needed)."""

from __future__ import annotations

import io
import logging
import os

import pandas as pd
import requests

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

logger = logging.getLogger(__name__)


def extract_folder_id_from_url(url: str) -> str | None:
    """Extract Google Drive folder ID from share URL."""
    if not url:
        return None
    if "/folders/" in url:
        return url.split("/folders/")[1].split("?")[0]
    if "?id=" in url:
        return url.split("?id=")[1].split("&")[0]
    # Assume it's already a folder ID
    return url


def list_public_drive_files(folder_id: str) -> list[dict] | None:
    """
    List all CSV/XLSX files from a public Google Drive folder.

    Args:
        folder_id: Google Drive folder ID (from share URL)

    Returns:
        List of dicts with 'id', 'name', 'mimeType', or None if API unavailable.
    """
    if not GOOGLE_API_AVAILABLE:
        logger.warning("Google API client not available; install google-api-python-client")
        return None

    api_key = os.getenv("GOOGLE_DRIVE_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_DRIVE_API_KEY environment variable not set")
        return None

    try:
        service = build("drive", "v3", developerKey=api_key)
        query = f"'{folder_id}' in parents and (mimeType='text/csv' or mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or mimeType='application/vnd.ms-excel') and trashed=false"
        results = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="files(id, name, mimeType, createdTime, modifiedTime, size)",
                pageSize=100,
            )
            .execute()
        )
        files = results.get("files", [])
        logger.info(f"Found {len(files)} CSV/XLSX files in folder {folder_id}")
        return files
    except HttpError as e:
        logger.error(f"Google Drive API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Error listing drive files: {e}")
        return None


def get_public_file_from_drive_id(file_id: str, file_name: str | None = None) -> pd.DataFrame | None:
    """
    Download a file from Google Drive by its file ID and parse into DataFrame.

    Args:
        file_id: Google Drive file ID
        file_name: Optional file name for format detection

    Returns:
        Parsed DataFrame or None if download/parse fails.
    """
    try:
        # Use the direct download URL for Google Drive files
        url = f"https://drive.google.com/uc?id={file_id}&export=download"
        logger.info(f"Fetching Google Drive file: {file_id}")

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        content = response.content
        logger.info(f"Downloaded {len(content)} bytes from Google Drive")

        # Detect file type
        if (file_name and file_name.lower().endswith(".xlsx")) or (file_name and file_name.lower().endswith(".xls")):
            df = pd.read_excel(io.BytesIO(content))
        elif file_name and file_name.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            # Try CSV first, then Excel
            try:
                df = pd.read_csv(io.BytesIO(content))
            except Exception:
                df = pd.read_excel(io.BytesIO(content))

        logger.info(f"Successfully parsed {len(df)} rows from Google Drive file")
        return df

    except requests.RequestException as e:
        logger.error(f"Failed to download file from Google Drive: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to parse Google Drive file: {e}")
        return None


def get_public_file_from_upload(file_name: str, content: bytes) -> pd.DataFrame | None:
    """Parse an uploaded CSV/XLS/XLSX file payload into a DataFrame."""
    if not content:
        logger.warning("uploaded file content is empty")
        return None

    normalized_name = (file_name or "").lower()

    try:
        if normalized_name.endswith(".xlsx") or normalized_name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
        elif normalized_name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            # Fallback parser order: CSV first, then Excel.
            try:
                df = pd.read_csv(io.BytesIO(content))
            except Exception:
                df = pd.read_excel(io.BytesIO(content))

        logger.info(f"Successfully parsed {len(df)} rows from uploaded file")
        return df
    except Exception as e:
        logger.error(f"Failed to parse uploaded file: {e}")
        return None


def get_public_file_from_url(file_url: str) -> pd.DataFrame | None:
    """
    Fetch a CSV or XLSX file from a public URL and parse into DataFrame.

    Supports:
    - Direct download links from Google Drive (https://drive.google.com/uc?id=...)
    - Public HTTPS URLs to CSV/XLSX files
    - Google Drive share links (auto-converts to download link)

    Args:
        file_url: Public URL to a CSV/XLSX file

    Returns:
        Parsed DataFrame or None if fetch/parse fails.
    """
    if not file_url:
        logger.warning("file_url is empty")
        return None

    # Normalize Google Drive share links to direct download links
    if "drive.google.com" in file_url:
        if "/d/" in file_url:
            # Extract file ID from share URL: https://drive.google.com/file/d/{FILE_ID}/view
            parts = file_url.split("/d/")
            if len(parts) > 1:
                file_id = parts[1].split("/")[0]
                file_url = f"https://drive.google.com/uc?id={file_id}&export=download"
        elif "?id=" in file_url:
            # Already in download format
            if "export=download" not in file_url:
                file_url += "&export=download"

    logger.info(f"Fetching file from URL: {file_url}")

    try:
        # Download with timeout
        response = requests.get(file_url, timeout=30)
        response.raise_for_status()

        content = response.content
        logger.info(f"Downloaded {len(content)} bytes")

        # Detect file type from content or URL
        if file_url.lower().endswith(".xlsx") or file_url.lower().endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
        elif file_url.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            # Try both; CSV first since it's more common
            try:
                df = pd.read_csv(io.BytesIO(content))
            except Exception:
                df = pd.read_excel(io.BytesIO(content))

        logger.info(f"Successfully parsed {len(df)} rows from file")
        return df

    except requests.RequestException as e:
        logger.error(f"Failed to download file: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to parse file: {e}")
        return None


def normalize_drive_data(df: pd.DataFrame) -> dict:
    """
    Convert raw DataFrame into normalized chart-ready data structure.

    Extracts ALL numeric columns for comprehensive visualization.

    Expected DataFrame columns (case-insensitive):
    - timestamp / date (or separate date + time columns)
    - city_name / city / location (optional; uses "Unknown" if missing)
    - ghi / global_irradiance / radiation / ghi_pyr
    - ambient_temp / temperature / temp / air_temperature
    - Any other numeric columns (power, humidity, wind, irradiance variants, etc.)

    Returns:
        Dict with keys: daily[], by_city[], scatter[], recent[], timeseries[], all_columns[]
    """
    if df is None or df.empty:
        return {
            "daily": [],
            "by_city": [],
            "scatter": [],
            "recent": [],
            "timeseries": [],
            "all_columns": [],
            "total_points": 0,
        }

    # Normalize column names (case-insensitive)
    df.columns = [col.lower().replace(" ", "_") for col in df.columns]

    # If separate date and time columns exist, combine them
    if "date" in df.columns and "time" in df.columns:
        df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"], errors="coerce")
        timestamp_col = "timestamp"
    else:
        # Map potential timestamp column names
        timestamp_col = next((c for c in df.columns if c in ["timestamp", "datetime"]), None)

    # Map potential column names
    city_col = next((c for c in df.columns if c in ["city_name", "city", "location"]), None)
    ghi_col = next((c for c in df.columns if c in ["ghi", "global_irradiance", "radiation", "ghi_pyr"]), None)
    temp_col = next((c for c in df.columns if c in ["ambient_temp", "temperature", "temp", "air_temperature"]), None)

    if not all([timestamp_col, ghi_col, temp_col]):
        logger.error(
            f"Missing required columns. Found: {list(df.columns)}. "
            f"Need: timestamp (or date+time), ghi (or ghi_pyr), temp (or air_temperature)"
        )
        return {
            "daily": [],
            "by_city": [],
            "scatter": [],
            "recent": [],
            "timeseries": [],
            "all_columns": [],
            "total_points": 0,
        }

    # Ensure proper data types
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
    df[ghi_col] = pd.to_numeric(df[ghi_col], errors="coerce")
    df[temp_col] = pd.to_numeric(df[temp_col], errors="coerce")

    # If city column is missing, create a default one
    if not city_col:
        df["city"] = "Unknown"
        city_col = "city"
    else:
        df[city_col] = df[city_col].fillna("Unknown")

    # Remove rows with missing timestamp, GHI, or temp
    df = df.dropna(subset=[timestamp_col, ghi_col, temp_col])

    if df.empty:
        return {
            "daily": [],
            "by_city": [],
            "scatter": [],
            "recent": [],
            "timeseries": [],
            "all_columns": [],
            "total_points": 0,
        }

    # Identify all numeric columns (exclude date/time)
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    
    # Map common column name variants to standardized names
    col_mapping = {
        "power_average_w_normalized": "power_avg_w",
        "ghi_pyr": "ghi_w_m2",
        "ghi": "ghi_w_m2",
        "dni": "ni_w_m2",
        "dhi": "dhi_w_m2",
        "air_temperature": "ambient_temp_c",
        "temperature": "ambient_temp_c",
        "temp": "ambient_temp_c",
        "relative_humidity": "relative_humidity_pct",
        "wind_speed": "wind_speed_m_s",
    }

    # Daily aggregates (last 60 days)
    df["date"] = df[timestamp_col].dt.date
    daily_data = (
        df.groupby("date")
        .agg({ghi_col: "mean", temp_col: "mean"})
        .reset_index()
        .sort_values("date")
        .tail(60)
    )
    daily = [
        {
            "date_utc": str(row["date"]),
            "avg_ghi": round(row[ghi_col], 2),
            "avg_temp": round(row[temp_col], 2),
        }
        for _, row in daily_data.iterrows()
    ]

    # By-city aggregates
    city_data = (
        df.groupby(city_col).agg({ghi_col: "mean", temp_col: "mean"}).reset_index().sort_values(city_col)
    )
    by_city = [
        {
            "city": row[city_col],
            "avg_ghi": round(row[ghi_col], 2),
            "avg_temp": round(row[temp_col], 2),
        }
        for _, row in city_data.iterrows()
    ]

    # Scatter plot (GHI vs Temp)
    scatter_df = df[[ghi_col, temp_col]].dropna().tail(250)
    scatter = [
        {"ghi": round(row[ghi_col], 2), "temp": round(row[temp_col], 2)}
        for _, row in scatter_df.iterrows()
    ]

    # Recent points (legacy)
    recent_df = df[[timestamp_col, city_col, ghi_col, temp_col]].sort_values(timestamp_col, ascending=False).head(120)
    recent = [
        {
            "timestamp_utc": row[timestamp_col].isoformat(),
            "city": row[city_col],
            "ghi": round(row[ghi_col], 2),
            "temp": round(row[temp_col], 2),
        }
        for _, row in recent_df.iterrows()
    ]

    # Comprehensive time series with ALL numeric columns
    ts_df = df[[timestamp_col, city_col] + numeric_cols].sort_values(timestamp_col, ascending=False).head(500)
    timeseries = []
    for _, row in ts_df.iterrows():
        ts_point = {
            "timestamp_utc": row[timestamp_col].isoformat(),
            "city": row[city_col],
        }
        # Map and include all numeric columns
        for col in numeric_cols:
            val = row[col]
            mapped_name = col_mapping.get(col, col)
            ts_point[mapped_name] = round(val, 2) if pd.notna(val) else None
        timeseries.append(ts_point)

    # Extract list of all available columns (for frontend to know what to chart)
    all_columns = [
        col_mapping.get(col, col) 
        for col in numeric_cols 
        if col not in [timestamp_col, city_col]
    ]

    return {
        "daily": daily,
        "by_city": by_city,
        "scatter": scatter,
        "recent": recent,
        "timeseries": timeseries,
        "all_columns": list(set(all_columns)),  # unique list
        "total_points": len(df),
    }
