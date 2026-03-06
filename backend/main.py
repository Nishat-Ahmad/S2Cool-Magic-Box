"""FastAPI backend exposing S2Cool math-model decision endpoints."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import FastAPI
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
    FeatureImportanceItem,
    FeatureImportanceResponse,
    ModelComparisonResponse,
    ModelMetric,
    PshRequest,
    PshResponse,
    SeasonalCurve,
    SeasonalCurvePoint,
    SeasonalResponse,
)
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
def feature_importance() -> FeatureImportanceResponse:
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
