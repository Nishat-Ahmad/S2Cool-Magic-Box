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
    DailyAutoSimulationRequest,
    DailyAutoSimulationResponse,
    DailyProfilePoint,
    DailySimulationRequest,
    DailySimulationResponse,
    DecisionRequest,
    DecisionResponse,
    PshRequest,
    PshResponse,
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
