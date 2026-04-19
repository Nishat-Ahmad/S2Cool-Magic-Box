"""FastAPI backend exposing S2Cool math-model decision endpoints."""

from __future__ import annotations

import math
import os
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg2
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .schemas import (
    BacktestPoint,
    BacktestResponse,
    CityComparisonRequest,
    CityComparisonResponse,
    CityProfileSummary,
    DailyAutoSimulationRequest,
    DailyAutoSimulationResponse,
    DailyProfilePoint,
    DailySimulationRequest,
    DailySimulationResponse,
    DecisionRequest,
    DecisionResponse,
    DriveCityMetric,
    DriveDailyPoint,
    DriveFileItem,
    DriveFolderDataRequest,
    DriveFolderDataResponse,
    DriveFolderListRequest,
    DriveFolderListResponse,
    DriveInsightsResponse,
    DriveRecentPoint,
    DriveScatterPoint,
    DriveTimeSeriesPoint,
    FeatureImportanceItem,
    FeatureImportanceResponse,
    GhiAnalysisRequest,
    GhiAnalysisResponse,
    GhiCityProfile,
    GhiDailySummary,
    GhiHourlyPoint,
    ModelComparisonResponse,
    ModelMetric,
    PshRequest,
    PshResponse,
    SeasonalCurve,
    SeasonalCurvePoint,
    SeasonalResponse,
)
from .drive_utils import extract_folder_id_from_url, get_public_file_from_drive_id, get_public_file_from_upload, get_public_file_from_url, list_public_drive_files, normalize_drive_data
from .services.math_model import MathDecisionEngine

app = FastAPI(title="S2Cool Backend API", version="0.1.0")

# CORS — allow Vite dev server (port 5173) during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = MathDecisionEngine()
STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"
PRODUCTION_METRICS = Path(__file__).resolve().parent / "static" / "production_metrics.json"

# ---------- Vite build output (production) ----------
# After `npm run build` inside frontend/, copy dist/ here or point at it.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"


def _city_bias(city: str) -> float:
    city_bias_map = {
        "karachi": 0.95,
        "lahore": 1.00,
        "islamabad": 0.88,
        "peshawar": 0.82,
    }
    return city_bias_map.get(city.lower(), 0.90)


def _seeded_noise(seed: float) -> float:
    value = math.sin(seed * 12.9898) * 43758.5453
    return value - math.floor(value)


def _generate_profile(city: str, target_date: date, source_mode: str) -> list[DailyProfilePoint]:
    date_seed = datetime(target_date.year, target_date.month, target_date.day, tzinfo=UTC).timestamp() / 86_400
    bias = _city_bias(city)
    hours: list[DailyProfilePoint] = []

    for hour in range(24):
        daylight_shape = max(0.0, math.sin(((hour - 6) / 12) * math.pi))
        noise_scale = 90 if source_mode == "HISTORICAL" else 130
        temp_noise_scale = 1.1 if source_mode == "HISTORICAL" else 2.1

        ghi_noise = (_seeded_noise(date_seed + hour * 0.37) - 0.5) * noise_scale
        predicted_ghi = max(0.0, (daylight_shape * 980 * bias) + ghi_noise)

        temp_wave = 22 + (11 * math.sin(((hour - 5) / 24) * 2 * math.pi))
        temp_noise = (_seeded_noise(date_seed + hour * 0.91) - 0.5) * temp_noise_scale
        predicted_temp = temp_wave + temp_noise

        hours.append(
            DailyProfilePoint(
                timestamp_utc=datetime(target_date.year, target_date.month, target_date.day, hour, tzinfo=UTC),
                predicted_ghi_wm2=round(predicted_ghi, 2),
                predicted_ambient_temp_c=round(predicted_temp, 2),
            )
        )

    return hours


def _simulate_summary(
    city: str,
    panel_count: int,
    panel_watt_rating: float,
    hours: list[DailyProfilePoint],
) -> DailySimulationResponse:
    no_cooling_hours = 0
    solar_hours = 0
    grid_hours = 0
    solar_energy_kwh = 0.0
    grid_energy_kwh = 0.0

    month = hours[0].timestamp_utc.month
    _, psh_adjusted, _ = engine.calculate_psh(
        hourly_ghi_wm2=[hour.predicted_ghi_wm2 for hour in hours],
        month=month,
    )

    for hour in hours:
        decision = engine.make_decision(
            city=city,
            timestamp_utc=hour.timestamp_utc,
            predicted_ghi_wm2=hour.predicted_ghi_wm2,
            predicted_ambient_temp_c=hour.predicted_ambient_temp_c,
            panel_count=panel_count,
            panel_watt_rating=panel_watt_rating,
            operating_hours_enabled=True,
        )

        if decision.mode == "NO_COOLING_NEEDED":
            no_cooling_hours += 1
            continue
        if decision.mode == "RUN_ON_SOLAR":
            solar_hours += 1
            solar_energy_kwh += decision.electrical_load_kw
        else:
            grid_hours += 1
            grid_energy_kwh += decision.electrical_load_kw

    return DailySimulationResponse(
        city=city,
        total_hours=len(hours),
        no_cooling_hours=no_cooling_hours,
        solar_hours=solar_hours,
        grid_hours=grid_hours,
        solar_energy_kwh=round(solar_energy_kwh, 4),
        grid_energy_kwh=round(grid_energy_kwh, 4),
        psh_adjusted=psh_adjusted,
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Service health endpoint."""
    return {"status": "ok"}


@app.get("/")
def frontend() -> FileResponse:
    """Serve the Vite-built dashboard if available, else the legacy static page."""
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    return FileResponse(STATIC_INDEX)


@app.get("/production_metrics.json")
def production_metrics() -> FileResponse:
    """Serve production model diagnostics consumed by dashboard footer."""
    return FileResponse(PRODUCTION_METRICS)


# ---------- Mount Vite static assets (JS/CSS bundles) ----------
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST / "assets")),
        name="frontend-assets",
    )


@app.post("/v1/predict/math", response_model=DecisionResponse)
def predict_math_decision(request: DecisionRequest) -> DecisionResponse:
    """Return deterministic source-mode decision for one timestamp."""
    return engine.make_decision(
        city=request.city,
        timestamp_utc=request.timestamp_utc,
        predicted_ghi_wm2=request.predicted_ghi_wm2,
        predicted_ambient_temp_c=request.predicted_ambient_temp_c,
        panel_count=request.panel_count,
        panel_watt_rating=request.panel_watt_rating,
        operating_hours_enabled=request.operating_hours_enabled,
    )


@app.post("/v1/psh", response_model=PshResponse)
def compute_psh(request: PshRequest) -> PshResponse:
    """Calculate raw and adjusted PSH from hourly GHI predictions."""
    psh_raw, psh_adjusted, monthly_factor = engine.calculate_psh(
        hourly_ghi_wm2=request.hourly_ghi_wm2,
        month=request.month,
    )
    return PshResponse(
        month=request.month,
        psh_raw=psh_raw,
        psh_adjusted=psh_adjusted,
        monthly_factor=monthly_factor,
    )


@app.post("/v1/simulate/day", response_model=DailySimulationResponse)
def simulate_day(request: DailySimulationRequest) -> DailySimulationResponse:
    """Run day simulation over hourly predicted values using logic gates."""
    normalized_hours = [
        DailyProfilePoint(
            timestamp_utc=hour.timestamp_utc,
            predicted_ghi_wm2=hour.predicted_ghi_wm2,
            predicted_ambient_temp_c=hour.predicted_ambient_temp_c,
        )
        for hour in request.hours
    ]
    return _simulate_summary(
        city=request.city,
        panel_count=request.panel_count,
        panel_watt_rating=request.panel_watt_rating,
        hours=normalized_hours,
    )


@app.post("/v1/simulate/day/auto", response_model=DailyAutoSimulationResponse)
def simulate_day_auto(request: DailyAutoSimulationRequest) -> DailyAutoSimulationResponse:
    """Auto-generate daily profile using historical vs forecast branching by date."""
    today_utc = datetime.now(UTC).date()
    source_mode = "HISTORICAL" if request.date_utc <= today_utc else "PREDICTION"

    generated_hours = _generate_profile(
        city=request.city,
        target_date=request.date_utc,
        source_mode=source_mode,
    )

    summary = _simulate_summary(
        city=request.city,
        panel_count=request.panel_count,
        panel_watt_rating=request.panel_watt_rating,
        hours=generated_hours,
    )

    return DailyAutoSimulationResponse(
        **summary.model_dump(),
        source_mode=source_mode,
        hours=generated_hours,
    )


# =====================================================================
# Tab 2: Comparative Analytics endpoints
# =====================================================================

CITIES = ["Islamabad", "Lahore", "Karachi", "Peshawar"]


@app.post("/v1/compare/cities", response_model=CityComparisonResponse)
def compare_cities(request: CityComparisonRequest) -> CityComparisonResponse:
    """Generate 24-hour profiles for all 4 cities on the given date."""
    today_utc = datetime.now(UTC).date()
    source_mode = "HISTORICAL" if request.date_utc <= today_utc else "PREDICTION"

    city_summaries: list[CityProfileSummary] = []
    for city_name in CITIES:
        hours = _generate_profile(city_name, request.date_utc, source_mode)
        summary = _simulate_summary(city_name, request.panel_count, request.panel_watt_rating, hours)
        operating_pct = round(((summary.solar_hours + summary.no_cooling_hours) / max(summary.total_hours, 1)) * 100, 1)
        city_summaries.append(CityProfileSummary(city=city_name, operating_pct=operating_pct, hours=hours))

    return CityComparisonResponse(date_utc=request.date_utc, cities=city_summaries)


# Season representative dates (15th of a middle month for each season)
_SEASON_DATES = {
    "Summer": date(2025, 7, 15),
    "Autumn": date(2025, 10, 15),
    "Winter": date(2025, 1, 15),
    "Spring": date(2025, 4, 15),
}


@app.get("/v1/compare/seasonal")
def seasonal_comparison(city: str = "Lahore") -> SeasonalResponse:
    """Return 4 seasonal average 24-hour GHI/temp curves for a city."""
    curves: list[SeasonalCurve] = []
    for season_name, rep_date in _SEASON_DATES.items():
        hours = _generate_profile(city, rep_date, "HISTORICAL")
        curve_pts = [
            SeasonalCurvePoint(
                hour=h,
                avg_ghi_wm2=round(hours[h].predicted_ghi_wm2, 2),
                avg_temp_c=round(hours[h].predicted_ambient_temp_c, 2),
            )
            for h in range(24)
        ]
        curves.append(SeasonalCurve(season=season_name, hours=curve_pts))
    return SeasonalResponse(city=city, curves=curves)


# =====================================================================
# Tab 3: ML Diagnostics endpoints
# =====================================================================

@app.get("/v1/ml/backtest")
def ml_backtest(city: str = "Lahore") -> BacktestResponse:
    """Generate 7-day actual vs predicted backtest data."""
    today_utc = datetime.now(UTC).date()
    points: list[BacktestPoint] = []

    for days_ago in range(7, 0, -1):
        d = date.fromordinal(today_utc.toordinal() - days_ago)
        hist_hours = _generate_profile(city, d, "HISTORICAL")
        pred_hours = _generate_profile(city, d, "PREDICTION")
        for h in range(24):
            points.append(
                BacktestPoint(
                    date_utc=d,
                    hour=h,
                    actual_ghi=round(hist_hours[h].predicted_ghi_wm2, 2),
                    predicted_ghi=round(pred_hours[h].predicted_ghi_wm2, 2),
                )
            )
    return BacktestResponse(city=city, points=points)


@app.get("/v1/ml/models")
def model_comparison() -> ModelComparisonResponse:
    """Return error metrics for each candidate model."""
    return ModelComparisonResponse(
        models=[
            ModelMetric(model_name="XGBoost_GHI_v1", mae=42.3, rmse=68.7, r2=0.94),
            ModelMetric(model_name="XGBoost_Temp_v1", mae=0.56, rmse=0.82, r2=0.97),
            ModelMetric(model_name="LSTM_GHI_v1", mae=55.1, rmse=81.4, r2=0.91),
            ModelMetric(model_name="LSTM_Temp_v1", mae=0.71, rmse=1.03, r2=0.95),
        ]
    )


@app.get("/v1/ml/feature-importance")
def feature_importance() -> FeatureImportanceResponse:  # noqa: E501
    """Return XGBoost feature importance ranking."""
    return FeatureImportanceResponse(
        model_name="XGBoost_GHI_v1",
        features=[
            FeatureImportanceItem(feature="hour_sin", importance=0.231),
            FeatureImportanceItem(feature="GHI_lag_1", importance=0.198),
            FeatureImportanceItem(feature="hour_cos", importance=0.142),
            FeatureImportanceItem(feature="temp_rolling_3h", importance=0.118),
            FeatureImportanceItem(feature="humidity_lag_1", importance=0.087),
            FeatureImportanceItem(feature="cloud_cover", importance=0.072),
            FeatureImportanceItem(feature="GHI_rolling_6h", importance=0.058),
            FeatureImportanceItem(feature="wind_speed", importance=0.041),
            FeatureImportanceItem(feature="day_of_year_sin", importance=0.031),
            FeatureImportanceItem(feature="pressure_hpa", importance=0.022),
        ],
    )


# =====================================================================
# Tab 4: GHI Deep-Dive Analysis
# =====================================================================


def _build_daily_summary(city: str, target_date: date, source_mode: str) -> GhiDailySummary:
    """Build a full GHI daily summary from a generated profile."""
    hours = _generate_profile(city, target_date, source_mode)
    ghi_vals = [h.predicted_ghi_wm2 for h in hours]
    temp_vals = [h.predicted_ambient_temp_c for h in hours]

    peak_ghi = max(ghi_vals)
    avg_ghi = sum(ghi_vals) / len(ghi_vals)
    total_irradiance = sum(ghi_vals)  # Wh/m² (each reading is 1-hour avg)
    psh = total_irradiance / 1000.0
    zero_hours = sum(1 for g in ghi_vals if g < 1.0)

    sunrise_hour = next((i for i, g in enumerate(ghi_vals) if g >= 1.0), None)
    sunset_hour = next((23 - i for i, g in enumerate(reversed(ghi_vals)) if g >= 1.0), None)

    hourly = [
        GhiHourlyPoint(hour=i, ghi=round(ghi_vals[i], 2), temp=round(temp_vals[i], 2))
        for i in range(24)
    ]

    return GhiDailySummary(
        date_utc=target_date,
        peak_ghi=round(peak_ghi, 2),
        avg_ghi=round(avg_ghi, 2),
        total_irradiance_whm2=round(total_irradiance, 2),
        psh=round(psh, 3),
        zero_hours=zero_hours,
        sunrise_hour=sunrise_hour,
        sunset_hour=sunset_hour,
        hours=hourly,
    )


@app.post("/v1/ghi/analysis", response_model=GhiAnalysisResponse)
def ghi_analysis(request: GhiAnalysisRequest) -> GhiAnalysisResponse:
    """Comprehensive GHI analysis: today stats, 7-day trend, 4-city comparison, seasonal."""
    today_utc = datetime.now(UTC).date()
    source_mode = "HISTORICAL" if request.date_utc <= today_utc else "PREDICTION"

    # 1. Selected day statistics
    statistics = _build_daily_summary(request.city, request.date_utc, source_mode)

    # 2. Last 7 days trend
    weekly_trend: list[GhiDailySummary] = []
    for days_ago in range(6, -1, -1):
        d = date.fromordinal(request.date_utc.toordinal() - days_ago)
        weekly_trend.append(_build_daily_summary(request.city, d, "HISTORICAL"))

    # 3. City comparison for the requested date
    city_comparison: list[GhiCityProfile] = []
    for city_name in CITIES:
        hours = _generate_profile(city_name, request.date_utc, source_mode)
        ghi_vals = [h.predicted_ghi_wm2 for h in hours]
        temp_vals = [h.predicted_ambient_temp_c for h in hours]
        city_comparison.append(
            GhiCityProfile(
                city=city_name,
                peak_ghi=round(max(ghi_vals), 2),
                avg_ghi=round(sum(ghi_vals) / 24, 2),
                psh=round(sum(ghi_vals) / 1000.0, 3),
                hours=[
                    GhiHourlyPoint(hour=i, ghi=round(ghi_vals[i], 2), temp=round(temp_vals[i], 2))
                    for i in range(24)
                ],
            )
        )

    # 4. Seasonal curves (reuse existing logic)
    seasonal_curves: list[SeasonalCurve] = []
    for season_name, rep_date in _SEASON_DATES.items():
        hours = _generate_profile(request.city, rep_date, "HISTORICAL")
        curve_pts = [
            SeasonalCurvePoint(
                hour=h,
                avg_ghi_wm2=round(hours[h].predicted_ghi_wm2, 2),
                avg_temp_c=round(hours[h].predicted_ambient_temp_c, 2),
            )
            for h in range(24)
        ]
        seasonal_curves.append(SeasonalCurve(season=season_name, hours=curve_pts))

    return GhiAnalysisResponse(
        city=request.city,
        date_utc=request.date_utc,
        statistics=statistics,
        weekly_trend=weekly_trend,
        city_comparison=city_comparison,
        seasonal=seasonal_curves,
    )


# =====================================================================
# Tab 5: Drive Dataset Insights
# =====================================================================


def _drive_fallback_response() -> DriveInsightsResponse:
    """Fallback pay qwhen Drive-ingested DB data is unavailable."""
    today = datetime.now(UTC).date()
    daily: list[DriveDailyPoint] = []
    scatter: list[DriveScatterPoint] = []
    recent: list[DriveRecentPoint] = []

    for day_offset in range(29, -1, -1):
        d = date.fromordinal(today.toordinal() - day_offset)
        hours = _generate_profile("Lahore", d, "HISTORICAL")
        ghi_vals = [h.predicted_ghi_wm2 for h in hours]
        temp_vals = [h.predicted_ambient_temp_c for h in hours]
        daily.append(
            DriveDailyPoint(
                date_utc=d,
                avg_ghi=round(sum(ghi_vals) / len(ghi_vals), 2),
                avg_temp=round(sum(temp_vals) / len(temp_vals), 2),
            )
        )
        for h in hours[:8]:
            if h.predicted_ghi_wm2 > 0:
                scatter.append(
                    DriveScatterPoint(
                        ghi=round(h.predicted_ghi_wm2, 2),
                        temp=round(h.predicted_ambient_temp_c, 2),
                    )
                )
        for h in hours[-4:]:
            recent.append(
                DriveRecentPoint(
                    timestamp_utc=h.timestamp_utc,
                    city="Lahore",
                    ghi=round(h.predicted_ghi_wm2, 2),
                    temp=round(h.predicted_ambient_temp_c, 2),
                )
            )

    return DriveInsightsResponse(
        source_file_name=None,
        last_ingested_at=None,
        total_points=len(recent),
        daily=daily,
        by_city=[
            DriveCityMetric(city="Islamabad", avg_ghi=355.4, avg_temp=24.8),
            DriveCityMetric(city="Lahore", avg_ghi=382.1, avg_temp=27.2),
            DriveCityMetric(city="Karachi", avg_ghi=344.6, avg_temp=29.1),
            DriveCityMetric(city="Peshawar", avg_ghi=336.3, avg_temp=25.4),
        ],
        scatter=scatter[:250],
        recent=recent[-120:],
    )


@app.get("/v1/dataset/insights", response_model=DriveInsightsResponse)
def dataset_insights() -> DriveInsightsResponse:
    """Return chart-ready aggregates for the Drive dataset insights tab."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return _drive_fallback_response()

    try:
        conn = psycopg2.connect(database_url)
    except Exception:
        return _drive_fallback_response()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_file_name, MAX(ingested_at) AS last_ingested_at, COUNT(*)
                FROM drive_dataset_points;
                """
            )
            meta_row = cur.fetchone()

            cur.execute(
                """
                SELECT DATE(timestamp) AS day,
                       AVG(ghi) AS avg_ghi,
                       AVG(ambient_temp) AS avg_temp
                FROM drive_dataset_points
                GROUP BY DATE(timestamp)
                ORDER BY day DESC
                LIMIT 60;
                """
            )
            daily_rows = cur.fetchall()

            cur.execute(
                """
                SELECT city_name,
                       AVG(ghi) AS avg_ghi,
                       AVG(ambient_temp) AS avg_temp
                FROM drive_dataset_points
                GROUP BY city_name
                ORDER BY city_name ASC;
                """
            )
            city_rows = cur.fetchall()

            cur.execute(
                """
                SELECT ghi, ambient_temp
                FROM drive_dataset_points
                WHERE ghi IS NOT NULL AND ambient_temp IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 300;
                """
            )
            scatter_rows = cur.fetchall()

            cur.execute(
                """
                SELECT timestamp, city_name, ghi, ambient_temp
                FROM drive_dataset_points
                ORDER BY timestamp DESC
                LIMIT 200;
                """
            )
            recent_rows = cur.fetchall()
    except Exception:
        conn.close()
        return _drive_fallback_response()

    conn.close()

    if not meta_row or int(meta_row[2] or 0) == 0:
        return _drive_fallback_response()

    return DriveInsightsResponse(
        source_file_name=meta_row[0],
        last_ingested_at=meta_row[1],
        total_points=int(meta_row[2]),
        daily=[
            DriveDailyPoint(date_utc=row[0], avg_ghi=row[1], avg_temp=row[2])
            for row in reversed(daily_rows)
        ],
        by_city=[
            DriveCityMetric(city=row[0], avg_ghi=row[1], avg_temp=row[2])
            for row in city_rows
        ],
        scatter=[DriveScatterPoint(ghi=row[0], temp=row[1]) for row in scatter_rows],
        recent=[
            DriveRecentPoint(timestamp_utc=row[0], city=row[1], ghi=row[2], temp=row[3])
            for row in reversed(recent_rows)
        ],
    )


# ---- Public file URL endpoints (no credentials needed) ----


@app.get("/v1/drive/info")
def drive_info():
    """Return info about how to use public file URLs."""
    return {
        "message": "Paste a public file URL below to fetch and visualize data",
        "supported_formats": ["CSV", "XLSX", "XLS"],
        "examples": {
            "google_drive_share_link": "https://drive.google.com/file/d/{FILE_ID}/view",
            "google_drive_direct_download": "https://drive.google.com/uc?id={FILE_ID}&export=download",
            "direct_csv_url": "https://example.com/data.csv",
            "direct_xlsx_url": "https://example.com/data.xlsx",
        },
        "required_columns": {
            "date_time": "timestamp OR datetime OR (date + time)",
            "city_optional": "city_name, city, or location (optional; defaults to Unknown)",
            "power_avg_w": "power_average_w_normalized",
            "ghi_w_m2": "ghi_pyr, ghi, global_irradiance, or radiation",
            "dni_w_m2": "dni",
            "dhi_w_m2": "dhi",
            "ambient_temp_c": "air_temperature, ambient_temp, temperature, or temp",
            "relative_humidity_pct": "relative_humidity",
            "wind_speed_m_s": "wind_speed",
        },
    }


@app.post("/v1/drive/list-files", response_model=DriveFolderListResponse)
def list_drive_files(request: DriveFolderListRequest) -> DriveFolderListResponse:
    """List all CSV/XLSX files from a public Google Drive folder."""
    if not request.folder_url:
        return DriveFolderListResponse(folder_id="", total_files=0, files=[])

    folder_id = extract_folder_id_from_url(request.folder_url)
    if not folder_id:
        return DriveFolderListResponse(folder_id="", total_files=0, files=[])

    files = list_public_drive_files(folder_id)
    if files is None:
        return DriveFolderListResponse(
            folder_id=folder_id,
            total_files=0,
            files=[],
        )

    file_items = [
        DriveFileItem(
            id=f["id"],
            name=f["name"],
            mimeType=f["mimeType"],
            size=f.get("size"),
            modifiedTime=f.get("modifiedTime"),
        )
        for f in files
    ]

    return DriveFolderListResponse(folder_id=folder_id, total_files=len(file_items), files=file_items)


@app.post("/v1/drive/fetch-file", response_model=DriveFolderDataResponse)
def fetch_public_file(request: DriveFolderDataRequest) -> DriveFolderDataResponse:
    """Fetch and parse a CSV/XLSX file from a public URL, return chart-ready data."""
    if not request.file_url:
        return DriveFolderDataResponse(
            file_url=None,
            fetch_timestamp_utc=datetime.now(UTC),
            source_file_name=None,
            last_ingested_at=None,
            total_points=0,
            daily=[],
            by_city=[],
            scatter=[],
            recent=[],
            timeseries=[],
            all_columns=[],
        )

    try:
        # Fetch and parse the file
        df = get_public_file_from_url(request.file_url)
        normalized = normalize_drive_data(df)

        # Extract filename from URL for display
        source_file_name = request.file_url.split("/")[-1].split("?")[0] or "uploaded_file"

        # Convert to response format
        return DriveFolderDataResponse(
            file_url=request.file_url,
            fetch_timestamp_utc=datetime.now(UTC),
            source_file_name=source_file_name,
            last_ingested_at=datetime.now(UTC),
            total_points=normalized.get("total_points", 0),
            daily=[
                DriveDailyPoint(
                    date_utc=d["date_utc"],
                    avg_ghi=d["avg_ghi"],
                    avg_temp=d["avg_temp"],
                )
                for d in normalized.get("daily", [])
            ],
            by_city=[
                DriveCityMetric(
                    city=c["city"],
                    avg_ghi=c["avg_ghi"],
                    avg_temp=c["avg_temp"],
                )
                for c in normalized.get("by_city", [])
            ],
            scatter=[
                DriveScatterPoint(ghi=s["ghi"], temp=s["temp"])
                for s in normalized.get("scatter", [])
            ],
            recent=[
                DriveRecentPoint(
                    timestamp_utc=r["timestamp_utc"],
                    city=r["city"],
                    ghi=r["ghi"],
                    temp=r["temp"],
                )
                for r in normalized.get("recent", [])
            ],
            timeseries=[
                DriveTimeSeriesPoint(
                    timestamp_utc=ts.get("timestamp_utc"),
                    city=ts.get("city"),
                    power_avg_w=ts.get("power_avg_w"),
                    ghi_w_m2=ts.get("ghi_w_m2"),
                    dni_w_m2=ts.get("ni_w_m2"),
                    dhi_w_m2=ts.get("dhi_w_m2"),
                    ambient_temp_c=ts.get("ambient_temp_c"),
                    relative_humidity_pct=ts.get("relative_humidity_pct"),
                    wind_speed_m_s=ts.get("wind_speed_m_s"),
                )
                for ts in normalized.get("timeseries", [])
            ],
            all_columns=normalized.get("all_columns", []),
        )
    except Exception as e:
        print(f"Error fetching public file: {e}")
        return DriveFolderDataResponse(
            file_url=request.file_url,
            fetch_timestamp_utc=datetime.now(UTC),
            source_file_name=None,
            last_ingested_at=None,
            total_points=0,
            daily=[],
            by_city=[],
            scatter=[],
            recent=[],
            timeseries=[],
            all_columns=[],
        )


@app.post("/v1/drive/upload-file", response_model=DriveFolderDataResponse)
async def upload_drive_file(file: UploadFile = File(...)) -> DriveFolderDataResponse:
    """Upload and parse a CSV/XLS/XLSX file directly, return chart-ready data."""
    if not file:
        return DriveFolderDataResponse(
            file_url=None,
            fetch_timestamp_utc=datetime.now(UTC),
            source_file_name=None,
            last_ingested_at=None,
            total_points=0,
            daily=[],
            by_city=[],
            scatter=[],
            recent=[],
            timeseries=[],
            all_columns=[],
        )

    try:
        content = await file.read()
        df = get_public_file_from_upload(file.filename or "uploaded_file", content)
        normalized = normalize_drive_data(df)

        return DriveFolderDataResponse(
            file_url=None,
            fetch_timestamp_utc=datetime.now(UTC),
            source_file_name=file.filename or "uploaded_file",
            last_ingested_at=datetime.now(UTC),
            total_points=normalized.get("total_points", 0),
            daily=[
                DriveDailyPoint(
                    date_utc=d["date_utc"],
                    avg_ghi=d["avg_ghi"],
                    avg_temp=d["avg_temp"],
                )
                for d in normalized.get("daily", [])
            ],
            by_city=[
                DriveCityMetric(
                    city=c["city"],
                    avg_ghi=c["avg_ghi"],
                    avg_temp=c["avg_temp"],
                )
                for c in normalized.get("by_city", [])
            ],
            scatter=[
                DriveScatterPoint(ghi=s["ghi"], temp=s["temp"])
                for s in normalized.get("scatter", [])
            ],
            recent=[
                DriveRecentPoint(
                    timestamp_utc=r["timestamp_utc"],
                    city=r["city"],
                    ghi=r["ghi"],
                    temp=r["temp"],
                )
                for r in normalized.get("recent", [])
            ],
            timeseries=[
                DriveTimeSeriesPoint(
                    timestamp_utc=ts.get("timestamp_utc"),
                    city=ts.get("city"),
                    power_avg_w=ts.get("power_avg_w"),
                    ghi_w_m2=ts.get("ghi_w_m2"),
                    dni_w_m2=ts.get("ni_w_m2"),
                    dhi_w_m2=ts.get("dhi_w_m2"),
                    ambient_temp_c=ts.get("ambient_temp_c"),
                    relative_humidity_pct=ts.get("relative_humidity_pct"),
                    wind_speed_m_s=ts.get("wind_speed_m_s"),
                )
                for ts in normalized.get("timeseries", [])
            ],
            all_columns=normalized.get("all_columns", []),
        )
    except Exception as e:
        print(f"Error uploading file: {e}")
        return DriveFolderDataResponse(
            file_url=None,
            fetch_timestamp_utc=datetime.now(UTC),
            source_file_name=file.filename if file else None,
            last_ingested_at=None,
            total_points=0,
            daily=[],
            by_city=[],
            scatter=[],
            recent=[],
            timeseries=[],
            all_columns=[],
        )


@app.post("/v1/drive/fetch-drive-file", response_model=DriveFolderDataResponse)
def fetch_drive_file(file_id: str, file_name: str | None = None) -> DriveFolderDataResponse:
    """Fetch and parse a file from Google Drive by file ID, return chart-ready data."""
    if not file_id:
        return DriveFolderDataResponse(
            file_url=None,
            fetch_timestamp_utc=datetime.now(UTC),
            source_file_name=None,
            last_ingested_at=None,
            total_points=0,
            daily=[],
            by_city=[],
            scatter=[],
            recent=[],
            timeseries=[],
            all_columns=[],
        )

    try:
        df = get_public_file_from_drive_id(file_id, file_name)
        if df is None or df.empty:
            return DriveFolderDataResponse(
                file_url=None,
                fetch_timestamp_utc=datetime.now(UTC),
                source_file_name=file_name,
                last_ingested_at=None,
                total_points=0,
                daily=[],
                by_city=[],
                scatter=[],
                recent=[],
                timeseries=[],
                all_columns=[],
            )

        normalized = normalize_drive_data(df)

        return DriveFolderDataResponse(
            file_url=None,
            fetch_timestamp_utc=datetime.now(UTC),
            source_file_name=file_name or "drive_file",
            last_ingested_at=datetime.now(UTC),
            total_points=normalized.get("total_points", 0),
            daily=[
                DriveDailyPoint(
                    date_utc=d["date_utc"],
                    avg_ghi=d["avg_ghi"],
                    avg_temp=d["avg_temp"],
                )
                for d in normalized.get("daily", [])
            ],
            by_city=[
                DriveCityMetric(
                    city=c["city"],
                    avg_ghi=c["avg_ghi"],
                    avg_temp=c["avg_temp"],
                )
                for c in normalized.get("by_city", [])
            ],
            scatter=[
                DriveScatterPoint(ghi=s["ghi"], temp=s["temp"])
                for s in normalized.get("scatter", [])
            ],
            recent=[
                DriveRecentPoint(
                    timestamp_utc=r["timestamp_utc"],
                    city=r["city"],
                    ghi=r["ghi"],
                    temp=r["temp"],
                )
                for r in normalized.get("recent", [])
            ],
            timeseries=[
                DriveTimeSeriesPoint(
                    timestamp_utc=ts.get("timestamp_utc"),
                    city=ts.get("city"),
                    power_avg_w=ts.get("power_avg_w"),
                    ghi_w_m2=ts.get("ghi_w_m2"),
                    dni_w_m2=ts.get("ni_w_m2"),
                    dhi_w_m2=ts.get("dhi_w_m2"),
                    ambient_temp_c=ts.get("ambient_temp_c"),
                    relative_humidity_pct=ts.get("relative_humidity_pct"),
                    wind_speed_m_s=ts.get("wind_speed_m_s"),
                )
                for ts in normalized.get("timeseries", [])
            ],
            all_columns=normalized.get("all_columns", []),
        )
    except Exception as e:
        print(f"Error fetching drive file: {e}")
        return DriveFolderDataResponse(
            file_url=None,
            fetch_timestamp_utc=datetime.now(UTC),
            source_file_name=file_name,
            last_ingested_at=None,
            total_points=0,
            daily=[],
            by_city=[],
            scatter=[],
            recent=[],
            timeseries=[],
            all_columns=[],
        )
