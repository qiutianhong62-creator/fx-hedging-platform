from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class MarketReference(BaseModel):
    spot: float
    observation_date: date
    is_live_quote: Literal[False] = False


class HistoricalVolatility(BaseModel):
    annualized_volatility_pct: float
    method: Literal["daily_log_returns_sample_stddev"] = (
        "daily_log_returns_sample_stddev"
    )
    trading_days_per_year: Literal[252] = 252
    window: Literal["1y"] = "1y"
    window_start: date
    window_end: date
    observation_count: int
    return_count: int


class MarketDataSource(BaseModel):
    provider: Literal["FRED"] = "FRED"
    series_id: Literal["DEXCHUS"] = "DEXCHUS"
    fetched_at_utc: datetime
    cache_status: Literal["live_fetch", "daily_cache", "stale_fallback"]
    cache_age_hours: float
    data_age_days: int
    is_stale: bool


class MarketHistorySummaryResponse(BaseModel):
    status: Literal["available"] = "available"
    currency_pair: Literal["USD/CNY"] = "USD/CNY"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    market_reference: MarketReference
    historical_volatility: HistoricalVolatility
    source: MarketDataSource
