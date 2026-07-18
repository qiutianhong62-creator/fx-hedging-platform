from datetime import date, timedelta
from math import isfinite
from typing import Sequence

from backend.forecast.errors import (
    ForecastAnchorRequiredError,
    ForecastHorizonInsufficientError,
    ForecastMaturityInvalidError,
    ForecastSourceInvalidError,
)
from backend.forecast.types import (
    ForecastAnchor,
    ForecastMatch,
    ForecastPoint,
)


MAX_MATURITY_DAYS = 365


def validate_maturity_date(
    valuation_date: date,
    maturity_date: date,
) -> None:
    if not (
        valuation_date < maturity_date
        <= valuation_date + timedelta(days=MAX_MATURITY_DAYS)
    ):
        raise ForecastMaturityInvalidError()


def _interpolate(
    maturity_date: date,
    before: ForecastAnchor,
    after: ForecastAnchor,
) -> ForecastMatch:
    total_days = (after.date - before.date).days
    elapsed_days = (maturity_date - before.date).days
    if total_days <= 0 or elapsed_days <= 0 or elapsed_days >= total_days:
        raise ForecastSourceInvalidError()
    weight = elapsed_days / total_days
    expected_spot = before.spot + weight * (after.spot - before.spot)
    if not isfinite(expected_spot) or expected_spot <= 0:
        raise ForecastSourceInvalidError()
    return ForecastMatch(
        expected_spot=expected_spot,
        method="interpolated",
        is_system_estimate=True,
        day_weight=weight,
        anchors=(before, after),
    )


def match_maturity_forecast(
    *,
    valuation_date: date,
    maturity_date: date,
    ing_points: Sequence[ForecastPoint],
    fred_anchor: ForecastAnchor | None = None,
) -> ForecastMatch:
    validate_maturity_date(valuation_date, maturity_date)
    future_points = tuple(
        item for item in ing_points if item.date > valuation_date
    )
    if not future_points or maturity_date > future_points[-1].date:
        raise ForecastHorizonInsufficientError()

    for point in future_points:
        if point.date == maturity_date:
            anchor = ForecastAnchor("ING", point.date, point.spot)
            return ForecastMatch(
                expected_spot=point.spot,
                method="direct",
                is_system_estimate=False,
                day_weight=None,
                anchors=(anchor,),
            )

    first = future_points[0]
    if maturity_date < first.date:
        if fred_anchor is None:
            raise ForecastAnchorRequiredError()
        if fred_anchor.date > valuation_date or fred_anchor.date >= maturity_date:
            raise ForecastSourceInvalidError()
        return _interpolate(
            maturity_date,
            fred_anchor,
            ForecastAnchor("ING", first.date, first.spot),
        )

    for before, after in zip(future_points, future_points[1:]):
        if before.date < maturity_date < after.date:
            return _interpolate(
                maturity_date,
                ForecastAnchor("ING", before.date, before.spot),
                ForecastAnchor("ING", after.date, after.spot),
            )
    raise ForecastHorizonInsufficientError()
