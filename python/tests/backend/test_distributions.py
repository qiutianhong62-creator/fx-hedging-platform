from datetime import date, timedelta

import pytest

from backend.services.distributions import build_lognormal_distribution


VALUATION_DATE = date(2030, 1, 1)


def make_distribution(*, days: int = 365, volatility_pct: float = 5.0):
    return build_lognormal_distribution(
        expected_spot=6.80,
        annualized_volatility_pct=volatility_pct,
        maturity_date=VALUATION_DATE + timedelta(days=days),
        valuation_date=VALUATION_DATE,
    )


def test_distribution_preserves_expected_spot_and_scales_volatility() -> None:
    distribution = make_distribution()

    assert distribution.horizon_days == 365
    assert distribution.term_volatility == pytest.approx(0.05)
    assert distribution.mean() == pytest.approx(6.80)


def test_distribution_returns_ordered_reference_quantiles() -> None:
    distribution = make_distribution()
    quantiles = [
        distribution.quantile(p)
        for p in (0.05, 0.25, 0.50, 0.75, 0.95)
    ]

    assert quantiles[0] < quantiles[1] < quantiles[2] < quantiles[3] < quantiles[4]
    assert quantiles[0] == pytest.approx(6.2553051696)
    assert quantiles[-1] == pytest.approx(7.3736681311)


def test_longer_horizon_produces_wider_distribution() -> None:
    one_year = make_distribution(days=365)
    two_years = make_distribution(days=730)

    assert two_years.quantile(0.05) < one_year.quantile(0.05)
    assert two_years.quantile(0.95) > one_year.quantile(0.95)


def test_higher_volatility_produces_wider_distribution() -> None:
    low = make_distribution(volatility_pct=3.0)
    high = make_distribution(volatility_pct=8.0)

    assert high.quantile(0.05) < low.quantile(0.05)
    assert high.quantile(0.95) > low.quantile(0.95)


def test_cdf_is_bounded_and_increases_with_spot() -> None:
    distribution = make_distribution()

    assert distribution.cdf(0) == 0.0
    assert 0 < distribution.cdf(6.50) < distribution.cdf(7.00) < 1


@pytest.mark.parametrize("probability", [0, 1, -0.1, 1.1])
def test_quantile_rejects_non_interior_probability(probability: float) -> None:
    with pytest.raises(ValueError, match="概率必须在 0 和 1 之间"):
        make_distribution().quantile(probability)


def test_distribution_rejects_non_future_maturity() -> None:
    with pytest.raises(ValueError, match="到期日必须晚于估值日"):
        build_lognormal_distribution(
            expected_spot=6.80,
            annualized_volatility_pct=5.0,
            maturity_date=VALUATION_DATE,
            valuation_date=VALUATION_DATE,
        )


def test_distribution_rejects_unrepresentable_parameters() -> None:
    from backend.services.distributions import ProbabilityCalculationError

    with pytest.raises(
        ProbabilityCalculationError,
        match="概率模型无法处理该组参数",
    ):
        make_distribution(volatility_pct=1e308)
