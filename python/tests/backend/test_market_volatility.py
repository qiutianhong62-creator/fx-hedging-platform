from datetime import date, timedelta

import pytest

from backend.market.types import FxObservation
from backend.market.volatility import (
    annualized_volatility_pct,
    daily_log_returns,
)


def observations(rates: list[float]) -> tuple[FxObservation, ...]:
    start = date(2030, 1, 1)
    return tuple(
        FxObservation(start + timedelta(days=index), rate)
        for index, rate in enumerate(rates)
    )


def test_daily_log_returns_use_adjacent_observations() -> None:
    returns = daily_log_returns(observations([6.80, 6.868, 6.79932]))

    assert returns == pytest.approx((0.00995033085, -0.01005033585))


def test_volatility_uses_sample_stddev_and_252_day_annualization() -> None:
    result = annualized_volatility_pct(
        observations([6.80, 6.868, 6.79932])
    )

    assert result == pytest.approx(22.450693, rel=1e-5)


def test_constant_rates_have_zero_historical_volatility() -> None:
    assert annualized_volatility_pct(observations([6.80, 6.80, 6.80])) == 0


def test_volatility_requires_three_price_observations() -> None:
    with pytest.raises(ValueError, match="至少需要3个汇率观察值"):
        annualized_volatility_pct(observations([6.80, 6.81]))
