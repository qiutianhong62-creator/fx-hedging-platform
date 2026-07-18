from math import log, sqrt
from statistics import stdev
from typing import Sequence

from backend.market.types import FxObservation


TRADING_DAYS_PER_YEAR = 252


def daily_log_returns(
    observations: Sequence[FxObservation],
) -> tuple[float, ...]:
    return tuple(
        log(current.rate / previous.rate)
        for previous, current in zip(observations, observations[1:])
    )


def annualized_volatility_pct(
    observations: Sequence[FxObservation],
) -> float:
    if len(observations) < 3:
        raise ValueError("至少需要3个汇率观察值")
    returns = daily_log_returns(observations)
    return stdev(returns) * sqrt(TRADING_DAYS_PER_YEAR) * 100
