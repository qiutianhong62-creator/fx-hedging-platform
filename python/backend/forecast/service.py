from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from backend.forecast.errors import (
    ForecastHorizonInsufficientError,
    ForecastSourceInvalidError,
    ForecastSourceStaleError,
    ForecastSourceUnavailableError,
    ForecastSourcesUnavailableError,
)
from backend.forecast.matcher import validate_maturity_date
from backend.forecast.schemas import (
    ForecastAnchorResponse,
    ForecastMatchingResponse,
    ForecastPointResponse,
    InstitutionForecastSourceResponse,
    MaturityForecastResponse,
    UnavailableForecastSourceResponse,
)
from backend.forecast.types import InstitutionMaturityEstimate


CONSENSUS_LIMITATIONS = [
    "当前仅包含ING和MUFG两家机构，不代表完整市场共识。",
    "两家机构暂时等权，没有使用历史准确率。",
    "插值结果是系统估算，不是机构对该具体日期的直接预测。",
    "机构预测可能与实际结果明显不同。",
]
FALLBACK_LIMITATIONS = CONSENSUS_LIMITATIONS + [
    "当前只有一家机构可用，结果不是多机构综合预测。",
    "不可用机构及原因已列在unavailable_sources中。",
    "另一机构恢复后，系统会重新使用50%/50%等权综合。",
]
REASON_CODES = {
    ForecastSourceUnavailableError: "fetch_failed",
    ForecastSourceInvalidError: "source_invalid",
    ForecastSourceStaleError: "source_stale",
    ForecastHorizonInsufficientError: "horizon_insufficient",
}
SOURCE_ERRORS = tuple(REASON_CODES)


class InstitutionEstimateLookup(Protocol):
    def get_estimate(
        self,
        valuation_date: date,
        maturity_date: date,
        *,
        now_utc: datetime,
    ) -> InstitutionMaturityEstimate: ...


class MaturityForecastService:
    def __init__(
        self,
        *,
        institution_services: tuple[
            tuple[str, InstitutionEstimateLookup],
            ...,
        ],
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self._institution_services = institution_services
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
        now = self._now_utc()
        validate_maturity_date(now.date(), maturity_date)
        successes: list[InstitutionMaturityEstimate] = []
        failures: list[UnavailableForecastSourceResponse] = []

        for institution, service in self._institution_services:
            try:
                successes.append(
                    service.get_estimate(
                        now.date(),
                        maturity_date,
                        now_utc=now,
                    )
                )
            except SOURCE_ERRORS as exc:
                failures.append(
                    UnavailableForecastSourceResponse(
                        institution=institution,
                        reason_code=REASON_CODES[type(exc)],
                    )
                )

        if not successes:
            if failures and all(
                item.reason_code == "horizon_insufficient"
                for item in failures
            ):
                raise ForecastHorizonInsufficientError()
            raise ForecastSourcesUnavailableError()

        is_consensus = len(successes) == 2
        weight = Decimal("0.5") if is_consensus else Decimal("1")
        expected_spot = sum(
            (
                Decimal(str(item.matched.expected_spot)) * weight
                for item in successes
            ),
            Decimal("0"),
        ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

        return MaturityForecastResponse(
            valuation_date=now.date(),
            maturity_date=maturity_date,
            expected_maturity_spot=float(expected_spot),
            source_count=len(successes),
            aggregation_status=(
                "equal_weight_consensus"
                if is_consensus
                else "single_source_fallback"
            ),
            is_consensus_forecast=is_consensus,
            sources=[
                _source_response(item, float(weight))
                for item in successes
            ],
            unavailable_sources=failures,
            limitations=(
                CONSENSUS_LIMITATIONS
                if is_consensus
                else FALLBACK_LIMITATIONS
            ),
        )


def _source_response(
    estimate: InstitutionMaturityEstimate,
    weight: float,
) -> InstitutionForecastSourceResponse:
    matched = estimate.matched
    snapshot = estimate.snapshot
    return InstitutionForecastSourceResponse(
        institution=estimate.institution,
        matched_maturity_spot=matched.expected_spot,
        weight=weight,
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
