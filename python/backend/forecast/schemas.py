from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


CacheStatus = Literal["live_fetch", "daily_cache", "stale_fallback"]


class ForecastPointResponse(BaseModel):
    date: date
    spot: float


class ForecastAnchorResponse(BaseModel):
    source: Literal["ING", "FRED"]
    date: date
    spot: float


class ForecastMatchingResponse(BaseModel):
    method: Literal["direct", "interpolated"]
    is_system_estimate: bool
    day_weight: float | None
    anchors: list[ForecastAnchorResponse]


class InstitutionForecastSourceResponse(BaseModel):
    institution: Literal["ING"] = "ING"
    source_updated_date: date
    source_url: str
    forecast_points: list[ForecastPointResponse]
    cache_status: CacheStatus
    fetched_at_utc: datetime
    cache_age_hours: float
    is_stale: bool


class MaturityForecastResponse(BaseModel):
    status: Literal["available"] = "available"
    currency_pair: Literal["USD/CNY"] = "USD/CNY"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    valuation_date: date
    maturity_date: date
    expected_maturity_spot: float
    matching: ForecastMatchingResponse
    source_count: Literal[1] = 1
    aggregation_status: Literal["single_source_trial"] = "single_source_trial"
    is_consensus_forecast: Literal[False] = False
    sources: list[InstitutionForecastSourceResponse]
    limitations: list[str]
