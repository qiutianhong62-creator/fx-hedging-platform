from decimal import Decimal

from backend.forward_strategy.schemas import (
    CoverageStatus,
    EconomicEffect,
    ForwardCoverage,
    ForwardDirection,
    ForwardLegResult,
    ForwardScenarioMetadata,
    ForwardStrategyScenarioRequest,
    ForwardStrategyScenarioResponse,
    ForwardTargetComparison,
    ForwardWarning,
)
from backend.models import ExposureType, ResultKind
from backend.services.scenario_common import (
    cny_amount,
    compare_target,
    decimal_value,
)


OVER_HEDGE_MESSAGE = (
    "远期总金额超过真实美元敞口，超额部分会产生额外方向性风险；"
    "本阶段未计算保证金、授信或额外资金占用。"
)


def _direction(exposure_type: ExposureType) -> ForwardDirection:
    if exposure_type is ExposureType.USD_PAYABLE:
        return ForwardDirection.BUY_USD
    return ForwardDirection.SELL_USD


def _effect(
    exposure_type: ExposureType,
    difference: Decimal,
) -> EconomicEffect:
    if difference == 0:
        return EconomicEffect.NO_CHANGE
    improvement = (
        difference < 0
        if exposure_type is ExposureType.USD_PAYABLE
        else difference > 0
    )
    return (
        EconomicEffect.IMPROVEMENT
        if improvement
        else EconomicEffect.WORSENING
    )


def calculate_forward_strategy_scenario(
    payload: ForwardStrategyScenarioRequest,
) -> ForwardStrategyScenarioResponse:
    exposure = decimal_value(payload.notional_usd)
    spot = decimal_value(payload.assumed_maturity_spot)
    direction = _direction(payload.exposure_type)
    raw_no_hedge = exposure * spot
    no_hedge_amount = cny_amount(raw_no_hedge)

    raw_leg_differences = [
        decimal_value(leg.notional_usd)
        * (decimal_value(leg.forward_rate) - spot)
        for leg in payload.forward_legs
    ]
    strategy_amount = cny_amount(
        raw_no_hedge + sum(raw_leg_differences, Decimal("0"))
    )
    total_difference = strategy_amount - no_hedge_amount

    leg_results: list[ForwardLegResult] = []
    for index, (leg, raw_difference) in enumerate(
        zip(payload.forward_legs, raw_leg_differences, strict=True),
        start=1,
    ):
        displayed_difference = cny_amount(raw_difference)
        leg_results.append(
            ForwardLegResult(
                leg_index=index,
                direction=direction,
                notional_usd=leg.notional_usd,
                forward_rate=leg.forward_rate,
                difference_cny=float(displayed_difference),
                economic_effect=_effect(
                    payload.exposure_type,
                    displayed_difference,
                ),
            )
        )

    total_notional = sum(
        (decimal_value(leg.notional_usd) for leg in payload.forward_legs),
        Decimal("0"),
    )
    unhedged = max(exposure - total_notional, Decimal("0"))
    overhedged = max(total_notional - exposure, Decimal("0"))
    if overhedged > 0:
        status = CoverageStatus.OVER_HEDGED
        warnings = [ForwardWarning(message=OVER_HEDGE_MESSAGE)]
    elif total_notional == exposure:
        status = CoverageStatus.FULL_HEDGE
        warnings = []
    else:
        status = CoverageStatus.PARTIAL_HEDGE
        warnings = []

    target = None
    if payload.target_cny is not None:
        no_hedge_target = compare_target(
            exposure_type=payload.exposure_type,
            amount_cny=no_hedge_amount,
            target_cny=payload.target_cny,
        )
        strategy_target = compare_target(
            exposure_type=payload.exposure_type,
            amount_cny=strategy_amount,
            target_cny=payload.target_cny,
        )
        if no_hedge_target is None or strategy_target is None:
            raise AssertionError("target comparison unexpectedly missing")
        target = ForwardTargetComparison(
            no_hedge=no_hedge_target,
            strategy=strategy_target,
        )

    result_kind = (
        ResultKind.CNY_COST
        if payload.exposure_type is ExposureType.USD_PAYABLE
        else ResultKind.CNY_PROCEEDS
    )
    return ForwardStrategyScenarioResponse(
        scenario=ForwardScenarioMetadata(
            assumed_maturity_spot=payload.assumed_maturity_spot,
            forward_direction=direction,
        ),
        result_kind=result_kind,
        no_hedge_amount_cny=float(no_hedge_amount),
        strategy_amount_cny=float(strategy_amount),
        strategy_minus_no_hedge_cny=float(total_difference),
        economic_effect=_effect(
            payload.exposure_type,
            total_difference,
        ),
        forward_legs=leg_results,
        coverage=ForwardCoverage(
            total_forward_notional_usd=float(total_notional),
            coverage_ratio=float(total_notional / exposure),
            unhedged_notional_usd=float(unhedged),
            overhedged_notional_usd=float(overhedged),
            status=status,
            warnings=warnings,
        ),
        target_comparison=target,
    )
