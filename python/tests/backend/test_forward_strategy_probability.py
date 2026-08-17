from datetime import date, timedelta

import pytest

from backend.forward_strategy.probability import (
    calculate_amount_range,
    calculate_forward_strategy_probability,
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


def calculate(payload: ForwardStrategyProbabilityRequest):
    return calculate_forward_strategy_probability(
        payload,
        expected_maturity_spot=6.72,
        annualized_volatility_pct=4.2,
        valuation_date=VALUATION_DATE,
        source_type="market_data",
        is_market_forecast=True,
    )


def assert_interval_difference_matches_spot_endpoints(
    payload: ForwardStrategyProbabilityRequest,
) -> None:
    result = calculate(payload)
    for interval in result.probability_profile.intervals:
        lower = scenario_amounts_at_spot(payload, interval.lower_spot)
        upper = scenario_amounts_at_spot(payload, interval.upper_spot)
        expected = sorted(
            [
                lower.strategy_amount_cny - lower.no_hedge_amount_cny,
                upper.strategy_amount_cny - upper.no_hedge_amount_cny,
            ]
        )
        assert (
            interval.strategy_minus_no_hedge.minimum_amount_cny
            == pytest.approx(expected[0], abs=0.01)
        )
        assert (
            interval.strategy_minus_no_hedge.maximum_amount_cny
            == pytest.approx(expected[1], abs=0.01)
        )


def test_partial_hedge_profile_returns_exact_difference_ranges() -> None:
    assert_interval_difference_matches_spot_endpoints(request())


def test_overhedged_profile_returns_exact_difference_ranges() -> None:
    assert_interval_difference_matches_spot_endpoints(
        request(
            legs=[{"notional_usd": 1_500_000, "forward_rate": 6.80}]
        )
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


def test_receivable_target_and_strategy_win_probabilities() -> None:
    result = calculate(request(target_cny=6_680_000))

    assert result.no_hedge.target_probability is not None
    assert result.forward_strategy.target_probability is not None
    assert result.no_hedge.target_probability.critical_spot == pytest.approx(
        6.68
    )
    assert 0 <= result.no_hedge.target_probability.probability_met <= 1
    assert (
        0
        <= result.forward_strategy.target_probability.probability_met
        <= 1
    )
    assert result.comparison.break_even_spot == pytest.approx(6.78)
    assert (
        result.comparison.probability_strategy_better
        + result.comparison.probability_no_hedge_better
        == pytest.approx(1.0)
    )


def test_payable_reverses_target_and_better_inequalities() -> None:
    receivable = calculate(request(target_cny=6_680_000))
    payable = calculate(
        request(exposure_type="usd_payable", target_cny=6_680_000)
    )

    assert receivable.no_hedge.target_probability is not None
    assert payable.no_hedge.target_probability is not None
    assert payable.no_hedge.target_probability.probability_met == pytest.approx(
        1 - receivable.no_hedge.target_probability.probability_met
    )
    assert payable.comparison.probability_strategy_better == pytest.approx(
        1 - receivable.comparison.probability_strategy_better
    )


def test_full_hedge_target_probability_is_zero_or_one() -> None:
    passing = calculate(
        request(
            target_cny=6_750_000,
            legs=[{"notional_usd": 1_000_000, "forward_rate": 6.80}],
        )
    )
    missing = calculate(
        request(
            target_cny=6_850_000,
            legs=[{"notional_usd": 1_000_000, "forward_rate": 6.80}],
        )
    )

    assert passing.forward_strategy.target_probability is not None
    assert passing.forward_strategy.target_probability.critical_spot is None
    assert passing.forward_strategy.target_probability.probability_met == 1
    assert missing.forward_strategy.target_probability is not None
    assert missing.forward_strategy.target_probability.probability_met == 0


def test_full_hedge_target_uses_same_cent_rounding_as_scenario() -> None:
    result = calculate(
        request(
            exposure_usd=1,
            target_cny=6.806,
            legs=[{"notional_usd": 1, "forward_rate": 6.805}],
        )
    )

    assert result.forward_strategy.expected_amount_cny == 6.81
    assert result.forward_strategy.target_probability is not None
    assert result.forward_strategy.target_probability.critical_spot is None
    assert result.forward_strategy.target_probability.probability_met == 1


def test_target_is_null_when_user_omits_it() -> None:
    result = calculate(request(target_cny=None))

    assert result.no_hedge.target_probability is None
    assert result.forward_strategy.target_probability is None


@pytest.mark.parametrize(
    "exposure_type",
    ["usd_receivable", "usd_payable", "usd_holding"],
)
def test_over_hedge_target_uses_correct_negative_slope_tail(
    exposure_type: str,
) -> None:
    result = calculate(
        request(
            exposure_type=exposure_type,
            target_cny=6_800_000,
            legs=[{"notional_usd": 1_500_000, "forward_rate": 6.80}],
        )
    )

    target = result.forward_strategy.target_probability
    assert target is not None
    assert target.critical_spot == pytest.approx(6.80)
    assert target.probability_met == pytest.approx(
        result.comparison.probability_strategy_better
    )
    expected_kind = (
        "cny_cost" if exposure_type == "usd_payable" else "cny_proceeds"
    )
    assert result.result_kind == expected_kind


@pytest.mark.parametrize(
    ("hedge_notional", "expected_change"),
    [
        (500_000, "reduced"),
        (2_000_000, "unchanged"),
        (2_500_000, "increased"),
    ],
)
def test_range_change_can_reduce_stay_equal_or_increase(
    hedge_notional: float,
    expected_change: str,
) -> None:
    result = calculate(
        request(
            legs=[
                {"notional_usd": hedge_notional, "forward_rate": 6.80}
            ]
        )
    )

    assert result.comparison.wide_range_90_width.change == expected_change


def test_profile_compares_no_hedge_and_strategy_on_same_spot_buckets() -> None:
    result = calculate(request())
    profile = result.probability_profile

    assert profile.bucket_count == 20
    assert len(profile.intervals) == 20
    first = profile.intervals[0]
    assert first.no_hedge.minimum_amount_cny < (
        first.no_hedge.maximum_amount_cny
    )
    assert first.forward_strategy.minimum_amount_cny < (
        first.forward_strategy.maximum_amount_cny
    )
    assert profile.lower_tail.no_hedge_amount_cny == pytest.approx(
        profile.lower_tail.boundary_spot * 1_000_000
    )
    total = (
        profile.lower_tail.probability
        + sum(item.interval_probability for item in profile.intervals)
        + profile.upper_tail.probability
    )
    assert total == pytest.approx(1.0)


def test_full_hedge_profile_has_fixed_strategy_amount() -> None:
    result = calculate(
        request(
            legs=[{"notional_usd": 1_000_000, "forward_rate": 6.80}]
        )
    )

    for interval in result.probability_profile.intervals:
        assert interval.forward_strategy.minimum_amount_cny == 6_800_000
        assert interval.forward_strategy.maximum_amount_cny == 6_800_000


def test_overhedged_profile_keeps_every_strategy_range_sorted() -> None:
    result = calculate(
        request(
            legs=[{"notional_usd": 1_500_000, "forward_rate": 6.80}]
        )
    )

    assert result.forward_strategy.coverage.status == "over_hedged"
    for interval in result.probability_profile.intervals:
        assert interval.forward_strategy.minimum_amount_cny <= (
            interval.forward_strategy.maximum_amount_cny
        )
