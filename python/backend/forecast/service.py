from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
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
from backend.forecast.schemas import (
    ForecastAnchorResponse,
    ForecastMatchingResponse,
    ForecastPointResponse,
    InstitutionForecastSourceResponse,
    MaturityForecastResponse,
)
from backend.forecast.types import (
    ForecastAnchor,
    ForecastProvider,
    InstitutionForecastSnapshot,
)


NORMAL_CACHE_TTL = timedelta(hours=24)
FALLBACK_CACHE_TTL = timedelta(days=7)
MAX_SOURCE_AGE_DAYS = 45
LIMITATIONS = [
    "这是单一机构试验，不是多机构共识预测。",
    "插值结果是系统估算，不是ING对当天的直接预测。",
]


class MarketHistoryLookup(Protocol):
    def get_summary(self): ...


class MaturityForecastService:
    def __init__(
        self,
        *,
        provider: ForecastProvider,
        cache: JsonForecastCache,
        market_history_service: MarketHistoryLookup,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._market_history_service = market_history_service
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
        now = self._now_utc()
        validate_maturity_date(now.date(), maturity_date)
        snapshot, cache_status = self._get_snapshot(now)
        source_age_days = (now.date() - snapshot.source_updated_date).days
        if source_age_days < 0:
            raise ForecastSourceInvalidError()
        if source_age_days > MAX_SOURCE_AGE_DAYS:
            raise ForecastSourceStaleError()
        if cache_status == "live_fetch":
            self._cache.save(snapshot)

        try:
            matched = match_maturity_forecast(
                valuation_date=now.date(),
                maturity_date=maturity_date,
                ing_points=snapshot.points,
            )
        except ForecastAnchorRequiredError:
            market_summary = self._market_history_service.get_summary()
            reference = market_summary.market_reference
            matched = match_maturity_forecast(
                valuation_date=now.date(),
                maturity_date=maturity_date,
                ing_points=snapshot.points,
                fred_anchor=ForecastAnchor(
                    source="FRED",
                    date=reference.observation_date,
                    spot=reference.spot,
                ),
            )

        cache_age_hours = max(
            0.0,
            (now - snapshot.fetched_at_utc).total_seconds() / 3600,
        )
        return MaturityForecastResponse(
            valuation_date=now.date(),
            maturity_date=maturity_date,
            expected_maturity_spot=matched.expected_spot,
            matching=ForecastMatchingResponse(
                method=matched.method,
                is_system_estimate=matched.is_system_estimate,
                day_weight=matched.day_weight,
                anchors=[
                    ForecastAnchorResponse(
                        source=item.source,
                        date=item.date,
                        spot=item.spot,
                    )
                    for item in matched.anchors
                ],
            ),
            sources=[
                InstitutionForecastSourceResponse(
                    source_updated_date=snapshot.source_updated_date,
                    source_url=snapshot.source_url,
                    forecast_points=[
                        ForecastPointResponse(date=item.date, spot=item.spot)
                        for item in snapshot.points
                    ],
                    cache_status=cache_status,
                    fetched_at_utc=snapshot.fetched_at_utc,
                    cache_age_hours=cache_age_hours,
                    is_stale=cache_status == "stale_fallback",
                )
            ],
            limitations=LIMITATIONS,
        )

    def _get_snapshot(
        self,
        now: datetime,
    ) -> tuple[InstitutionForecastSnapshot, str]:
        cached = self._cache.load()
        cache_age = None if cached is None else now - cached.fetched_at_utc
        if (
            cached is not None
            and cache_age is not None
            and timedelta(0) <= cache_age <= NORMAL_CACHE_TTL
        ):
            return cached, "daily_cache"
        try:
            return self._provider.fetch(now), "live_fetch"
        except ForecastFetchError as exc:
            if (
                cached is None
                or cache_age is None
                or cache_age < timedelta(0)
                or cache_age > FALLBACK_CACHE_TTL
            ):
                raise ForecastSourceUnavailableError() from exc
            return cached, "stale_fallback"
