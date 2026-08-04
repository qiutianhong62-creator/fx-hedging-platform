from collections.abc import Callable
from datetime import date, datetime, timezone

from backend.forecast.cache import JsonForecastCache
from backend.forecast.institution import (
    InstitutionForecastService,
    MarketHistoryLookup,
)
from backend.forecast.matcher import validate_maturity_date
from backend.forecast.schemas import (
    ForecastAnchorResponse,
    ForecastMatchingResponse,
    ForecastPointResponse,
    InstitutionForecastSourceResponse,
    MaturityForecastResponse,
)
from backend.forecast.types import ForecastProvider


LIMITATIONS = [
    "这是单一机构试验，不是多机构共识预测。",
    "插值结果是系统估算，不是ING对当天的直接预测。",
]


class MaturityForecastService:
    def __init__(
        self,
        *,
        provider: ForecastProvider,
        cache: JsonForecastCache,
        market_history_service: MarketHistoryLookup,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self._institution_service = InstitutionForecastService(
            provider=provider,
            cache=cache,
            market_history_service=market_history_service,
        )
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
        now = self._now_utc()
        validate_maturity_date(now.date(), maturity_date)
        estimate = self._institution_service.get_estimate(
            now.date(),
            maturity_date,
            now_utc=now,
        )
        snapshot = estimate.snapshot
        matched = estimate.matched
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
                    cache_status=estimate.cache_status,
                    fetched_at_utc=snapshot.fetched_at_utc,
                    cache_age_hours=estimate.cache_age_hours,
                    is_stale=estimate.is_stale,
                )
            ],
            limitations=LIMITATIONS,
        )
