from datetime import date, timedelta

from backend.forward_strategy.probability import (
    calculate_amount_range,
    scenario_amounts_at_spot,
)
from backend.forward_strategy.schemas import (
    ForwardStrategyProbabilityRequest,
)
from backend.services.distributions import build_lognormal_distribution


VALUATION_DATE = date.today()
MATURITY_DATE = VALUATION_DATE + timedelta(days=180)


def request(
    *,
    exposure_type: str = "usd_receivable",
    exposure_usd: float = 1_000_000,
    target_cny: float | None = None,
    legs: list[dict[str, float]] | None = None,
) -> ForwardStrategyProbabilityRequest:
    return ForwardStrategyProbabilityRequest(
        exposure_type=exposure_type,
        notional_usd=exposure_usd,
        maturity_date=MATURITY_DATE,
        target_cny=target_cny,
        forward_legs=legs or [
            {"notional_usd": 300_000, "forward_rate": 6.80},
            {"notional_usd": 200_000, "forward_rate": 6.75},
        ],
    )


def distribution():
    return build_lognormal_distribution(
        expected_spot=6.72,
        annualized_volatility_pct=4.2,
        maturity_date=MATURITY_DATE,
        valuation_date=VALUATION_DATE,
    )


def test_expected_amounts_reuse_scenario_cashflows() -> None:
    result = scenario_amounts_at_spot(request(), 6.72)

    assert result.no_hedge_amount_cny == 6_720_000
    assert result.strategy_amount_cny == 6_750_000
    assert result.coverage.coverage_ratio == 0.5


def test_partial_hedge_has_a_narrower_ordered_range() -> None:
    no_hedge = calculate_amount_range(
        request(),
        distribution(),
        probability=0.90,
        lower_percentile=0.05,
        upper_percentile=0.95,
        strategy=False,
    )
    strategy = calculate_amount_range(
        request(),
        distribution(),
        probability=0.90,
        lower_percentile=0.05,
        upper_percentile=0.95,
        strategy=True,
    )

    assert no_hedge.minimum_amount_cny < no_hedge.maximum_amount_cny
    assert strategy.minimum_amount_cny < strategy.maximum_amount_cny
    assert (
        strategy.maximum_amount_cny - strategy.minimum_amount_cny
        < no_hedge.maximum_amount_cny - no_hedge.minimum_amount_cny
    )


def test_full_hedge_has_one_fixed_amount() -> None:
    payload = request(
        legs=[{"notional_usd": 1_000_000, "forward_rate": 6.80}]
    )
    result = scenario_amounts_at_spot(payload, 6.72)
    amount_range = calculate_amount_range(
        payload,
        distribution(),
        probability=0.90,
        lower_percentile=0.05,
        upper_percentile=0.95,
        strategy=True,
    )

    assert result.strategy_amount_cny == 6_800_000
    assert amount_range.minimum_amount_cny == 6_800_000
    assert amount_range.maximum_amount_cny == 6_800_000


def test_over_hedge_range_is_sorted_when_amount_slope_is_negative() -> None:
    payload = request(
        legs=[{"notional_usd": 1_500_000, "forward_rate": 6.80}]
    )
    amount_range = calculate_amount_range(
        payload,
        distribution(),
        probability=0.90,
        lower_percentile=0.05,
        upper_percentile=0.95,
        strategy=True,
    )

    assert amount_range.minimum_amount_cny < amount_range.maximum_amount_cny
    scenario = scenario_amounts_at_spot(payload, 6.72)
    assert scenario.coverage.status == "over_hedged"
    assert scenario.coverage.warnings[0].code == "over_hedged"
