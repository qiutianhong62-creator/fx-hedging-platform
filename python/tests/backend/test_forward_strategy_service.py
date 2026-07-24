from datetime import date, timedelta

import pytest

from backend.forward_strategy.schemas import (
    CoverageStatus,
    EconomicEffect,
    ForwardDirection,
    ForwardStrategyScenarioRequest,
)
from backend.forward_strategy.service import (
    calculate_forward_strategy_scenario,
)


def request(
    *,
    exposure_type: str = "usd_receivable",
    exposure_usd: float = 1_000_000,
    target_cny: float | None = 6_680_000,
    spot: float = 6.60,
    legs: list[dict[str, float]] | None = None,
) -> ForwardStrategyScenarioRequest:
    return ForwardStrategyScenarioRequest(
        exposure_type=exposure_type,
        notional_usd=exposure_usd,
        maturity_date=date.today() + timedelta(days=180),
        target_cny=target_cny,
        assumed_maturity_spot=spot,
        forward_legs=legs or [
            {"notional_usd": 300_000, "forward_rate": 6.80},
            {"notional_usd": 200_000, "forward_rate": 6.75},
        ],
    )


def test_multiple_receivable_forwards_match_manual_calculation() -> None:
    result = calculate_forward_strategy_scenario(request())

    assert result.scenario.forward_direction is ForwardDirection.SELL_USD
    assert result.no_hedge_amount_cny == 6_600_000
    assert result.forward_legs[0].difference_cny == 60_000
    assert result.forward_legs[1].difference_cny == 30_000
    assert result.strategy_amount_cny == 6_690_000
    assert result.strategy_minus_no_hedge_cny == 90_000
    assert result.economic_effect is EconomicEffect.IMPROVEMENT
    assert result.coverage.coverage_ratio == 0.5
    assert result.coverage.unhedged_notional_usd == 500_000
    assert result.coverage.status is CoverageStatus.PARTIAL_HEDGE
    assert result.target_comparison is not None
    assert result.target_comparison.no_hedge.target_met is False
    assert result.target_comparison.strategy.target_met is True


def test_same_positive_difference_worsens_payable_cost() -> None:
    result = calculate_forward_strategy_scenario(
        request(exposure_type="usd_payable")
    )

    assert result.scenario.forward_direction is ForwardDirection.BUY_USD
    assert result.strategy_amount_cny == 6_690_000
    assert result.strategy_minus_no_hedge_cny == 90_000
    assert result.economic_effect is EconomicEffect.WORSENING
    assert all(
        leg.economic_effect is EconomicEffect.WORSENING
        for leg in result.forward_legs
    )


def test_usd_holding_uses_sell_direction_and_proceeds() -> None:
    result = calculate_forward_strategy_scenario(
        request(exposure_type="usd_holding", target_cny=None)
    )

    assert result.scenario.forward_direction is ForwardDirection.SELL_USD
    assert result.result_kind == "cny_proceeds"
    assert result.economic_effect is EconomicEffect.IMPROVEMENT


@pytest.mark.parametrize(
    ("total_notional", "expected_status"),
    [
        (1_000_000, CoverageStatus.FULL_HEDGE),
        (1_200_000, CoverageStatus.OVER_HEDGED),
    ],
)
def test_full_and_over_hedge_status(
    total_notional: float,
    expected_status: CoverageStatus,
) -> None:
    result = calculate_forward_strategy_scenario(
        request(
            target_cny=None,
            legs=[{"notional_usd": total_notional, "forward_rate": 6.80}],
        )
    )

    assert result.coverage.status is expected_status
    assert result.coverage.overhedged_notional_usd == max(
        total_notional - 1_000_000,
        0,
    )
    assert bool(result.coverage.warnings) is (
        expected_status is CoverageStatus.OVER_HEDGED
    )
    if expected_status is CoverageStatus.OVER_HEDGED:
        assert result.coverage.warnings[0].code == "over_hedged"
        assert "额外方向性风险" in result.coverage.warnings[0].message


def test_equal_forward_and_spot_rates_have_no_effect() -> None:
    result = calculate_forward_strategy_scenario(
        request(
            target_cny=None,
            legs=[{"notional_usd": 500_000, "forward_rate": 6.60}],
        )
    )

    assert result.strategy_minus_no_hedge_cny == 0
    assert result.economic_effect is EconomicEffect.NO_CHANGE
    assert result.forward_legs[0].economic_effect is EconomicEffect.NO_CHANGE
    assert result.target_comparison is None


def test_intermediate_values_are_not_rounded_before_sum() -> None:
    result = calculate_forward_strategy_scenario(
        request(
            exposure_usd=1,
            target_cny=None,
            spot=1,
            legs=[
                {"notional_usd": 1, "forward_rate": 1.005},
                {"notional_usd": 1, "forward_rate": 1.005},
            ],
        )
    )

    assert result.strategy_amount_cny == 1.01
