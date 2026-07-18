from datetime import date, timedelta

import pytest

from backend.forecast.errors import (
    ForecastAnchorRequiredError,
    ForecastHorizonInsufficientError,
    ForecastMaturityInvalidError,
)
from backend.forecast.matcher import match_maturity_forecast
from backend.forecast.types import ForecastAnchor, ForecastPoint


VALUATION_DATE = date(2026, 7, 18)
POINTS = (
    ForecastPoint(date(2026, 9, 30), 6.74),
    ForecastPoint(date(2026, 12, 31), 6.70),
    ForecastPoint(date(2027, 3, 31), 6.68),
)


def test_exact_ing_date_returns_direct_original_point() -> None:
    result = match_maturity_forecast(
        valuation_date=VALUATION_DATE,
        maturity_date=date(2026, 12, 31),
        ing_points=POINTS,
    )

    assert result.expected_spot == 6.70
    assert result.method == "direct"
    assert result.is_system_estimate is False
    assert result.day_weight is None
    assert result.anchors == (
        ForecastAnchor("ING", date(2026, 12, 31), 6.70),
    )


def test_between_ing_points_interpolates_by_natural_days() -> None:
    result = match_maturity_forecast(
        valuation_date=VALUATION_DATE,
        maturity_date=date(2026, 11, 15),
        ing_points=POINTS,
    )

    assert result.day_weight == pytest.approx(0.5)
    assert result.expected_spot == pytest.approx(6.72)
    assert [item.source for item in result.anchors] == ["ING", "ING"]


def test_before_first_ing_point_requires_and_uses_actual_fred_anchor() -> None:
    with pytest.raises(ForecastAnchorRequiredError):
        match_maturity_forecast(
            valuation_date=VALUATION_DATE,
            maturity_date=date(2026, 8, 15),
            ing_points=POINTS,
        )

    result = match_maturity_forecast(
        valuation_date=VALUATION_DATE,
        maturity_date=date(2026, 8, 15),
        ing_points=POINTS,
        fred_anchor=ForecastAnchor("FRED", date(2026, 7, 10), 6.7766),
    )

    expected_weight = 36 / 82
    assert result.day_weight == pytest.approx(expected_weight)
    assert result.expected_spot == pytest.approx(
        6.7766 + expected_weight * (6.74 - 6.7766)
    )
    assert result.anchors[0].date == date(2026, 7, 10)


@pytest.mark.parametrize(
    "maturity_date",
    [
        VALUATION_DATE,
        VALUATION_DATE - timedelta(days=1),
        VALUATION_DATE + timedelta(days=366),
    ],
)
def test_maturity_must_be_in_the_next_365_days(maturity_date: date) -> None:
    with pytest.raises(ForecastMaturityInvalidError):
        match_maturity_forecast(
            valuation_date=VALUATION_DATE,
            maturity_date=maturity_date,
            ing_points=POINTS,
        )


def test_matcher_never_extrapolates_after_last_ing_point() -> None:
    with pytest.raises(ForecastHorizonInsufficientError):
        match_maturity_forecast(
            valuation_date=VALUATION_DATE,
            maturity_date=date(2027, 4, 1),
            ing_points=POINTS,
        )
