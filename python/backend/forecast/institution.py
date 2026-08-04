from datetime import date, datetime, timedelta
from typing import Protocol

from backend.forecast.cache import JsonForecastCache
from backend.forecast.errors import (
    ForecastAnchorRequiredError,
    ForecastFetchError,
    ForecastSourceInvalidError,
    ForecastSourceStaleError,
    ForecastSourceUnavailableError,
)
from backend.forecast.matcher import (
    match_maturity_forecast,
    validate_maturity_date,
)
from backend.forecast.types import (
    ForecastAnchor,
    ForecastProvider,
    InstitutionForecastSnapshot,
    InstitutionMaturityEstimate,
)


NORMAL_CACHE_TTL = timedelta(hours=24)
FALLBACK_CACHE_TTL = timedelta(days=7)
MAX_SOURCE_AGE_DAYS = 45


class MarketHistoryLookup(Protocol):
    def get_summary(self): ...


class InstitutionForecastService:
    def __init__(
        self,
        *,
        provider: ForecastProvider,
        cache: JsonForecastCache,
        market_history_service: MarketHistoryLookup,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._market_history_service = market_history_service

    def get_estimate(
        self,
        valuation_date: date,
        maturity_date: date,
        *,
        now_utc: datetime,
    ) -> InstitutionMaturityEstimate:
        validate_maturity_date(valuation_date, maturity_date)
        snapshot, cache_status = self._get_snapshot(now_utc)
        source_age_days = (valuation_date - snapshot.source_updated_date).days
        if source_age_days < 0:
            raise ForecastSourceInvalidError()
        if source_age_days > MAX_SOURCE_AGE_DAYS:
            raise ForecastSourceStaleError()
        if cache_status == "live_fetch":
            self._cache.save(snapshot)

        try:
            matched = match_maturity_forecast(
                valuation_date=valuation_date,
                maturity_date=maturity_date,
                institution=snapshot.institution,
                forecast_points=snapshot.points,
            )
        except ForecastAnchorRequiredError:
            reference = self._market_history_service.get_summary().market_reference
            matched = match_maturity_forecast(
                valuation_date=valuation_date,
                maturity_date=maturity_date,
                institution=snapshot.institution,
                forecast_points=snapshot.points,
                fred_anchor=ForecastAnchor(
                    source="FRED",
                    date=reference.observation_date,
                    spot=reference.spot,
                ),
            )

        cache_age_hours = max(
            0.0,
            (now_utc - snapshot.fetched_at_utc).total_seconds() / 3600,
        )
        return InstitutionMaturityEstimate(
            institution=snapshot.institution,
            matched=matched,
            snapshot=snapshot,
            cache_status=cache_status,
            cache_age_hours=cache_age_hours,
            is_stale=cache_status == "stale_fallback",
        )

    def _get_snapshot(
        self,
        now_utc: datetime,
    ) -> tuple[InstitutionForecastSnapshot, str]:
        cached = self._cache.load()
        cache_age = (
            None if cached is None else now_utc - cached.fetched_at_utc
        )
        if (
            cached is not None
            and cache_age is not None
            and timedelta(0) <= cache_age <= NORMAL_CACHE_TTL
        ):
            return cached, "daily_cache"
        try:
            return self._provider.fetch(now_utc), "live_fetch"
        except ForecastFetchError as exc:
            if (
                cached is None
                or cache_age is None
                or cache_age < timedelta(0)
                or cache_age > FALLBACK_CACHE_TTL
            ):
                raise ForecastSourceUnavailableError() from exc
            return cached, "stale_fallback"
