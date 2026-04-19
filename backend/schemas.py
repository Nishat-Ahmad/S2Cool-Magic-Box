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


# ---- Tab 4: GHI Deep-Dive Analysis ----


class GhiAnalysisRequest(BaseModel):
    """Request for comprehensive GHI analysis data."""

    city: str
    date_utc: date


class GhiHourlyPoint(BaseModel):
    """One hour of GHI + temp data (lightweight)."""

    hour: int
    ghi: float
    temp: float


class GhiDailySummary(BaseModel):
    """One day's GHI summary plus hourly breakdown."""

    date_utc: date
    peak_ghi: float
    avg_ghi: float
    total_irradiance_whm2: float
    psh: float
    zero_hours: int
    sunrise_hour: int | None
    sunset_hour: int | None
    hours: list[GhiHourlyPoint]


class GhiCityProfile(BaseModel):
    """One city's GHI profile for a single date."""

    city: str
    peak_ghi: float
    avg_ghi: float
    psh: float
    hours: list[GhiHourlyPoint]


class GhiAnalysisResponse(BaseModel):
    """Comprehensive GHI analysis payload."""

    city: str
    date_utc: date
    statistics: GhiDailySummary
    weekly_trend: list[GhiDailySummary]
    city_comparison: list[GhiCityProfile]
    seasonal: list[SeasonalCurve]


# ---- Tab 5: Drive Dataset Insights ----


class DriveDailyPoint(BaseModel):
    """Daily aggregate point for Drive-ingested data."""

    date_utc: date
    avg_ghi: float | None = None
    avg_temp: float | None = None


class DriveCityMetric(BaseModel):
    """City-level aggregate metric from Drive-ingested data."""

    city: str
    avg_ghi: float | None = None
    avg_temp: float | None = None


class DriveScatterPoint(BaseModel):
    """One scatter point for GHI vs temperature."""

    ghi: float
    temp: float


class DriveRecentPoint(BaseModel):
    """Recent timestamp-level record for trend visualization."""

    timestamp_utc: datetime
    city: str
    ghi: float | None = None
    temp: float | None = None


class DriveTimeSeriesPoint(BaseModel):
    """One timestamp with all available metrics (comprehensive format)."""

    timestamp_utc: datetime
    city: str
    power_avg_w: float | None = None
    ghi_w_m2: float | None = None
    dni_w_m2: float | None = None
    dhi_w_m2: float | None = None
    ambient_temp_c: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_m_s: float | None = None


class DriveInsightsResponse(BaseModel):
    """Chart-ready payload for the Drive dataset insights tab."""

    source_file_name: str | None = None
    last_ingested_at: datetime | None = None
    total_points: int
    daily: list[DriveDailyPoint]
    by_city: list[DriveCityMetric]
    scatter: list[DriveScatterPoint]
    recent: list[DriveRecentPoint]


class DriveFolderDataRequest(BaseModel):
    """Request to fetch and parse data from a public file URL."""

    file_url: str = Field(..., description="Public URL to CSV/XLSX file (Google Drive or any source)")


class DriveFolderDataResponse(DriveInsightsResponse):
    """Chart-ready payload from on-demand public file fetch."""

    file_url: str | None = None
    fetch_timestamp_utc: datetime | None = None
    timeseries: list[DriveTimeSeriesPoint] | None = None


class DriveFileItem(BaseModel):
    """One file from a Google Drive folder listing."""

    id: str
    name: str
    mimeType: str
    size: int | None = None
    modifiedTime: str | None = None


class DriveFolderListResponse(BaseModel):
    """Response containing list of files from a Google Drive folder."""

    folder_id: str
    total_files: int
    files: list[DriveFileItem]


class DriveFolderListRequest(BaseModel):
    """Request to list files from a public Google Drive folder."""

    folder_url: str = Field(
        ...,
        description="Public Google Drive folder URL (e.g., https://drive.google.com/drive/folders/{FOLDER_ID})",
    )
