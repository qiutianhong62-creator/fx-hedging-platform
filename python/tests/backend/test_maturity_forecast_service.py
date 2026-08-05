from datetime import date, datetime, timezone

import pytest

from backend.forecast.errors import (
    ForecastHorizonInsufficientError,
    ForecastMaturityInvalidError,
    ForecastSourceInvalidError,
    ForecastSourceStaleError,
    ForecastSourceUnavailableError,
    ForecastSourcesUnavailableError,
)
from backend.forecast.ing import ING_FORECAST_URL
from backend.forecast.mufg import MUFG_FORECAST_URL
from backend.forecast.service import MaturityForecastService
from backend.forecast.types import (
    ForecastAnchor,
    ForecastMatch,
    ForecastPoint,
    InstitutionForecastSnapshot,
    InstitutionMaturityEstimate,
)


NOW = datetime(2026, 8, 4, 10, tzinfo=timezone.utc)
MATURITY_DATE = date(2026, 11, 15)


def estimate(
    institution: str,
    matched_spot: float,
) -> InstitutionMaturityEstimate:
    source_url = (
        ING_FORECAST_URL if institution == "ING" else MUFG_FORECAST_URL
    )
    first_spot = matched_spot + 0.02
    second_spot = matched_spot - 0.02
    snapshot = InstitutionForecastSnapshot(
        institution=institution,
        currency_pair="USD/CNY",
        source_url=source_url,
        source_updated_date=date(2026, 7, 20),
        fetched_at_utc=NOW,
        points=(
            ForecastPoint(date(2026, 9, 30), first_spot),
            ForecastPoint(date(2026, 12, 31), second_spot),
        ),
    )
    return InstitutionMaturityEstimate(
        institution=institution,
        matched=ForecastMatch(
            expected_spot=matched_spot,
            method="interpolated",
            is_system_estimate=True,
            day_weight=0.5,
            anchors=(
                ForecastAnchor(
                    institution,
                    date(2026, 9, 30),
                    first_spot,
                ),
                ForecastAnchor(
                    institution,
                    date(2026, 12, 31),
                    second_spot,
                ),
            ),
        ),
        snapshot=snapshot,
        cache_status="live_fetch",
        cache_age_hours=0,
        is_stale=False,
    )


class FakeInstitutionService:
    def __init__(
        self,
        *,
        result: InstitutionMaturityEstimate | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[date, date, datetime]] = []

    def get_estimate(
        self,
        valuation_date: date,
        maturity_date: date,
        *,
        now_utc: datetime,
    ) -> InstitutionMaturityEstimate:
        self.calls.append((valuation_date, maturity_date, now_utc))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def service(
    ing: FakeInstitutionService,
    mufg: FakeInstitutionService,
) -> MaturityForecastService:
    return MaturityForecastService(
        institution_services=(("ING", ing), ("MUFG", mufg)),
        now_utc=lambda: NOW,
    )


def test_two_sources_are_matched_first_then_equal_weighted() -> None:
    ing = FakeInstitutionService(result=estimate("ING", 6.68))
    mufg = FakeInstitutionService(result=estimate("MUFG", 6.62))

    result = service(ing, mufg).get_estimate(MATURITY_DATE)

    assert result.expected_maturity_spot == 6.65
    assert result.source_count == 2
    assert result.aggregation_status == "equal_weight_consensus"
    assert result.is_consensus_forecast is True
    assert [
        (item.institution, item.matched_maturity_spot, item.weight)
        for item in result.sources
    ] == [
        ("ING", 6.68, 0.5),
        ("MUFG", 6.62, 0.5),
    ]
    assert result.unavailable_sources == []
    assert [item.source for item in result.sources[1].matching.anchors] == [
        "MUFG",
        "MUFG",
    ]
    assert ing.calls == [(NOW.date(), MATURITY_DATE, NOW)]
    assert mufg.calls == [(NOW.date(), MATURITY_DATE, NOW)]


def test_consensus_rounds_result_to_six_decimal_places() -> None:
    result = service(
        FakeInstitutionService(result=estimate("ING", 6.1234567)),
        FakeInstitutionService(result=estimate("MUFG", 6.2345678)),
    ).get_estimate(MATURITY_DATE)

    assert result.expected_maturity_spot == 6.179013


def test_source_matched_spots_hide_binary_float_artifacts() -> None:
    result = service(
        FakeInstitutionService(result=estimate("ING", 6.720000000000001)),
        FakeInstitutionService(result=estimate("MUFG", 6.675000000000001)),
    ).get_estimate(MATURITY_DATE)

    assert [item.matched_maturity_spot for item in result.sources] == [
        6.72,
        6.675,
    ]


def test_consensus_is_reproducible_from_displayed_source_values() -> None:
    result = service(
        FakeInstitutionService(result=estimate("ING", 6.0)),
        FakeInstitutionService(result=estimate("MUFG", 6.0000005)),
    ).get_estimate(MATURITY_DATE)

    assert [item.matched_maturity_spot for item in result.sources] == [
        6.0,
        6.000001,
    ]
    assert result.expected_maturity_spot == 6.000001


@pytest.mark.parametrize(
    ("failed_name", "error", "reason_code"),
    [
        ("ING", ForecastSourceUnavailableError(), "fetch_failed"),
        ("MUFG", ForecastSourceInvalidError(), "source_invalid"),
        ("ING", ForecastSourceStaleError(), "source_stale"),
        (
            "MUFG",
            ForecastHorizonInsufficientError(),
            "horizon_insufficient",
        ),
    ],
)
def test_one_failed_source_returns_traceable_fallback(
    failed_name: str,
    error: Exception,
    reason_code: str,
) -> None:
    ing = FakeInstitutionService(result=estimate("ING", 6.68))
    mufg = FakeInstitutionService(result=estimate("MUFG", 6.62))
    failed = ing if failed_name == "ING" else mufg
    failed.result = None
    failed.error = error

    result = service(ing, mufg).get_estimate(MATURITY_DATE)

    expected_available = "MUFG" if failed_name == "ING" else "ING"
    assert result.source_count == 1
    assert result.aggregation_status == "single_source_fallback"
    assert result.is_consensus_forecast is False
    assert result.sources[0].institution == expected_available
    assert result.sources[0].weight == 1.0
    assert result.unavailable_sources[0].institution == failed_name
    assert result.unavailable_sources[0].reason_code == reason_code
    assert any("不是多机构综合预测" in item for item in result.limitations)


def test_two_horizon_failures_raise_horizon_insufficient() -> None:
    with pytest.raises(ForecastHorizonInsufficientError):
        service(
            FakeInstitutionService(error=ForecastHorizonInsufficientError()),
            FakeInstitutionService(error=ForecastHorizonInsufficientError()),
        ).get_estimate(MATURITY_DATE)


@pytest.mark.parametrize(
    ("ing_error", "mufg_error"),
    [
        (ForecastSourceUnavailableError(), ForecastSourceInvalidError()),
        (ForecastSourceStaleError(), ForecastSourceUnavailableError()),
        (
            ForecastHorizonInsufficientError(),
            ForecastSourceUnavailableError(),
        ),
    ],
)
def test_non_horizon_or_mixed_failures_raise_sources_unavailable(
    ing_error: Exception,
    mufg_error: Exception,
) -> None:
    with pytest.raises(ForecastSourcesUnavailableError):
        service(
            FakeInstitutionService(error=ing_error),
            FakeInstitutionService(error=mufg_error),
        ).get_estimate(MATURITY_DATE)


def test_invalid_maturity_stops_before_both_sources() -> None:
    ing = FakeInstitutionService(result=estimate("ING", 6.68))
    mufg = FakeInstitutionService(result=estimate("MUFG", 6.62))

    with pytest.raises(ForecastMaturityInvalidError):
        service(ing, mufg).get_estimate(NOW.date())

    assert ing.calls == []
    assert mufg.calls == []
