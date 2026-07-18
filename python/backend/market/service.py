from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from math import isfinite

from backend.market.cache import JsonHistoryCache
from backend.market.errors import (
    MarketDataFetchError,
    MarketDataInsufficientError,
    MarketDataInvalidError,
    MarketDataStaleError,
    MarketDataUnavailableError,
)
from backend.market.schemas import (
    HistoricalVolatility,
    MarketDataSource,
    MarketHistorySummaryResponse,
    MarketReference,
)
from backend.market.types import CachedHistory, HistoryProvider
from backend.market.volatility import annualized_volatility_pct


MINIMUM_OBSERVATIONS = 200
NORMAL_CACHE_TTL = timedelta(hours=24)
FALLBACK_CACHE_TTL = timedelta(days=7)
MAX_DATA_AGE_DAYS = 14
WINDOW_DAYS = 365


class MarketHistoryService:
    def __init__(
        self,
        *,
        provider: HistoryProvider,
        cache: JsonHistoryCache,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def get_summary(self) -> MarketHistorySummaryResponse:
        now = self._now_utc()
        cached = self._cache.load()
        cache_age = None if cached is None else now - cached.fetched_at_utc
        if (
            cached is not None
            and cache_age is not None
            and timedelta(0) <= cache_age <= NORMAL_CACHE_TTL
        ):
            return self._build_summary(cached, now, "daily_cache")

        query_end = now.date()
        query_start = query_end - timedelta(days=WINDOW_DAYS)
        try:
            observations = self._provider.fetch(query_start, query_end)
        except MarketDataFetchError as exc:
            if (
                cached is None
                or cache_age is None
                or cache_age < timedelta(0)
                or cache_age > FALLBACK_CACHE_TTL
            ):
                raise MarketDataUnavailableError() from exc
            return self._build_summary(cached, now, "stale_fallback")

        history = CachedHistory(
            provider="FRED",
            series_id="DEXCHUS",
            query_start=query_start,
            query_end=query_end,
            fetched_at_utc=now,
            observations=observations,
        )
        summary = self._build_summary(history, now, "live_fetch")
        self._cache.save(history)
        return summary

    def _build_summary(
        self,
        history: CachedHistory,
        now: datetime,
        cache_status: str,
    ) -> MarketHistorySummaryResponse:
        if len(history.observations) < MINIMUM_OBSERVATIONS:
            raise MarketDataInsufficientError()
        latest = history.observations[-1]
        data_age_days = (now.date() - latest.date).days
        if data_age_days < 0:
            raise MarketDataInvalidError()
        if data_age_days > MAX_DATA_AGE_DAYS:
            raise MarketDataStaleError()

        volatility = annualized_volatility_pct(history.observations)
        if not isfinite(volatility) or volatility <= 0:
            raise MarketDataInvalidError()
        cache_age_hours = max(
            0.0,
            (now - history.fetched_at_utc).total_seconds() / 3600,
        )

        return MarketHistorySummaryResponse(
            market_reference=MarketReference(
                spot=latest.rate,
                observation_date=latest.date,
            ),
            historical_volatility=HistoricalVolatility(
                annualized_volatility_pct=volatility,
                window_start=history.query_start,
                window_end=history.query_end,
                observation_count=len(history.observations),
                return_count=len(history.observations) - 1,
            ),
            source=MarketDataSource(
                fetched_at_utc=history.fetched_at_utc,
                cache_status=cache_status,
                cache_age_hours=cache_age_hours,
                data_age_days=data_age_days,
                is_stale=cache_status == "stale_fallback",
            ),
        )
