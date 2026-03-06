"""Pydantic request/response schemas for S2Cool backend endpoints."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class DecisionRequest(BaseModel):
    """Single-timestep hybrid cooling decision input."""

    city: str = Field(..., examples=["Lahore"])
    timestamp_utc: datetime
    predicted_ghi_wm2: float = Field(..., ge=0.0)
    predicted_ambient_temp_c: float
    panel_count: int = Field(default=10, ge=1)
    panel_watt_rating: float = Field(default=640.0, gt=0.0)
    operating_hours_enabled: bool = True


class DecisionResponse(BaseModel):
    """Single-timestep cooling source decision output."""

    city: str
    timestamp_utc: datetime
    mode: str
    cooling_needed: bool
    no_cooling_needed_banner: str | None = None
    predicted_ghi_wm2: float
    predicted_ambient_temp_c: float
    solar_generation_kw: float
    electrical_load_kw: float
    cooling_capacity_kw_thermal: float
    cop_ideal: float


class PshRequest(BaseModel):
    """Daily PSH request using predicted hourly GHI values."""

    month: int = Field(..., ge=1, le=12)
    hourly_ghi_wm2: list[float] = Field(..., min_length=1)


class PshResponse(BaseModel):
    """Peak Sun Hour output with monthly adjustment."""

    month: int
    psh_raw: float
    psh_adjusted: float
    monthly_factor: float


class DailyHourInput(BaseModel):
    """One hourly forecast point for daily simulation."""

    timestamp_utc: datetime
    predicted_ghi_wm2: float = Field(..., ge=0.0)
    predicted_ambient_temp_c: float


class DailySimulationRequest(BaseModel):
    """Daily simulation request over hourly predicted values."""

    city: str
    panel_count: int = Field(default=10, ge=1)
    panel_watt_rating: float = Field(default=640.0, gt=0.0)
    hours: list[DailyHourInput] = Field(..., min_length=1)


class DailySimulationResponse(BaseModel):
    """Daily simulation summary output."""

    city: str
    total_hours: int
    no_cooling_hours: int
    solar_hours: int
    grid_hours: int
    solar_energy_kwh: float
    grid_energy_kwh: float
    psh_adjusted: float


class DailyAutoSimulationRequest(BaseModel):
    """Daily simulation request where backend decides historical vs forecast source."""

    city: str
    date_utc: date
    panel_count: int = Field(default=10, ge=1)
    panel_watt_rating: float = Field(default=640.0, gt=0.0)


class DailyProfilePoint(BaseModel):
    """One generated hourly profile point for dashboard visualization."""

    timestamp_utc: datetime
    predicted_ghi_wm2: float = Field(..., ge=0.0)
    predicted_ambient_temp_c: float


class DailyAutoSimulationResponse(DailySimulationResponse):
    """Daily simulation summary plus profile and selected source mode."""

    source_mode: str
    hours: list[DailyProfilePoint]


# ---- Tab 2: Comparative Analytics ----


class CityComparisonRequest(BaseModel):
    """Request 4-city GHI + temp overlay for a single date."""

    date_utc: date
    panel_count: int = Field(default=10, ge=1)
    panel_watt_rating: float = Field(default=640.0, gt=0.0)


class CityProfileSummary(BaseModel):
    """One city's 24-hour profile plus operating percentage."""

    city: str
    operating_pct: float
    hours: list[DailyProfilePoint]


class CityComparisonResponse(BaseModel):
    """4-city comparison payload."""

    date_utc: date
    cities: list[CityProfileSummary]


class SeasonalCurvePoint(BaseModel):
    """One hour in a seasonal average curve."""

    hour: int
    avg_ghi_wm2: float
    avg_temp_c: float


class SeasonalCurve(BaseModel):
    """A named season's average 24-hour profile."""

    season: str
    hours: list[SeasonalCurvePoint]


class SeasonalResponse(BaseModel):
    """Seasonal comparison payload."""

    city: str
    curves: list[SeasonalCurve]


# ---- Tab 3: ML Diagnostics ----


class BacktestPoint(BaseModel):
    """Single point in the actual vs predicted backtest."""

    date_utc: date
    hour: int
    actual_ghi: float
    predicted_ghi: float


class BacktestResponse(BaseModel):
    """Week of actual vs predicted data for backtesting chart."""

    city: str
    points: list[BacktestPoint]


class ModelMetric(BaseModel):
    """Error metrics for one model."""

    model_name: str
    mae: float
    rmse: float
    r2: float


class ModelComparisonResponse(BaseModel):
    """Side-by-side metrics for all trained models."""

    models: list[ModelMetric]


class FeatureImportanceItem(BaseModel):
    """One feature and its importance weight."""

    feature: str
    importance: float


class FeatureImportanceResponse(BaseModel):
    """XGBoost feature importance payload."""

    model_name: str
    features: list[FeatureImportanceItem]
