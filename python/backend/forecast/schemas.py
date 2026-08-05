from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


CacheStatus = Literal["live_fetch", "daily_cache", "stale_fallback"]
InstitutionName = Literal["ING", "MUFG"]
UnavailableReason = Literal[
    "fetch_failed",
    "source_invalid",
    "source_stale",
    "horizon_insufficient",
]


class ForecastPointResponse(BaseModel):
    date: date
    spot: float


class ForecastAnchorResponse(BaseModel):
    source: Literal["ING", "MUFG", "FRED"]
    date: date
    spot: float


class ForecastMatchingResponse(BaseModel):
    method: Literal["direct", "interpolated"]
    is_system_estimate: bool
    day_weight: float | None
    anchors: list[ForecastAnchorResponse]


class InstitutionForecastSourceResponse(BaseModel):
    institution: InstitutionName
    matched_maturity_spot: float
    weight: Literal[0.5, 1.0]
    matching: ForecastMatchingResponse
    source_updated_date: date
    source_url: str
    forecast_points: list[ForecastPointResponse]
    cache_status: CacheStatus
    fetched_at_utc: datetime
    cache_age_hours: float
    is_stale: bool


class UnavailableForecastSourceResponse(BaseModel):
    institution: InstitutionName
    reason_code: UnavailableReason


class MaturityForecastResponse(BaseModel):
    status: Literal["available"] = "available"
    currency_pair: Literal["USD/CNY"] = "USD/CNY"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    valuation_date: date
    maturity_date: date
    expected_maturity_spot: float
    source_count: Literal[1, 2]
    aggregation_status: Literal[
        "equal_weight_consensus",
        "single_source_fallback",
    ]
    is_consensus_forecast: bool
    sources: list[InstitutionForecastSourceResponse]
    unavailable_sources: list[UnavailableForecastSourceResponse]
    limitations: list[str]
