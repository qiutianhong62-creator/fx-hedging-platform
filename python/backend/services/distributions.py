from dataclasses import dataclass
from datetime import date
from math import exp, isfinite, log, sqrt
from statistics import NormalDist


DAYS_PER_YEAR = 365
STANDARD_NORMAL = NormalDist()


class ProbabilityCalculationError(ValueError):
    pass


def _finite(value: float) -> float:
    if not isfinite(value):
        raise ProbabilityCalculationError("概率模型无法处理该组参数")
    return value


def _positive_finite(value: float) -> float:
    if value <= 0:
        raise ProbabilityCalculationError("概率模型无法处理该组参数")
    return _finite(value)


@dataclass(frozen=True)
class LognormalDistribution:
    expected_spot: float
    horizon_days: int
    term_volatility: float
    log_mean: float

    def mean(self) -> float:
        try:
            return _positive_finite(
                exp(self.log_mean + 0.5 * self.term_volatility**2)
            )
        except OverflowError as exc:
            raise ProbabilityCalculationError(
                "概率模型无法处理该组参数"
            ) from exc

    def quantile(self, probability: float) -> float:
        if not 0 < probability < 1:
            raise ValueError("概率必须在 0 和 1 之间")
        z_score = STANDARD_NORMAL.inv_cdf(probability)
        try:
            return _positive_finite(
                exp(self.log_mean + self.term_volatility * z_score)
            )
        except OverflowError as exc:
            raise ProbabilityCalculationError(
                "概率模型无法处理该组参数"
            ) from exc

    def cdf(self, spot: float) -> float:
        if spot <= 0:
            return 0.0
        z_score = (log(spot) - self.log_mean) / self.term_volatility
        return min(1.0, max(0.0, STANDARD_NORMAL.cdf(z_score)))


def build_lognormal_distribution(
    *,
    expected_spot: float,
    annualized_volatility_pct: float,
    maturity_date: date,
    valuation_date: date | None = None,
) -> LognormalDistribution:
    effective_valuation_date = valuation_date or date.today()
    horizon_days = (maturity_date - effective_valuation_date).days
    if horizon_days <= 0:
        raise ValueError("到期日必须晚于估值日")

    try:
        annualized_volatility = annualized_volatility_pct / 100
        term_volatility = _finite(
            annualized_volatility * sqrt(horizon_days / DAYS_PER_YEAR)
        )
        log_mean = _finite(log(expected_spot) - 0.5 * term_volatility**2)
    except OverflowError as exc:
        raise ProbabilityCalculationError(
            "概率模型无法处理该组参数"
        ) from exc

    return LognormalDistribution(
        expected_spot=expected_spot,
        horizon_days=horizon_days,
        term_volatility=term_volatility,
        log_mean=log_mean,
    )
