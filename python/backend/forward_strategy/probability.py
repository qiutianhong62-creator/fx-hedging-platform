from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from backend.forward_strategy.schemas import (
    AmountProbabilityRange,
    ForwardCoverage,
    ForwardProbabilityDistribution,
    ForwardStrategyProbabilityComparison,
    ForwardStrategyProbabilityRequest,
    ForwardStrategyProbabilityResponse,
    ForwardStrategyProbabilityResult,
    ForwardStrategyScenarioRequest,
    ForwardTargetProbability,
    RangeChange,
    RangeWidthComparison,
    SpotProbabilityRange,
    StrategyProbabilityResult,
)
from backend.forward_strategy.service import (
    calculate_forward_strategy_scenario,
)
from backend.models import ExposureType, ResultKind
from backend.services.distributions import (
    LognormalDistribution,
    build_lognormal_distribution,
)
from backend.services.scenario_common import cny_amount


@dataclass(frozen=True)
class ScenarioAmounts:
    result_kind: ResultKind
    no_hedge_amount_cny: float
    strategy_amount_cny: float
    coverage: ForwardCoverage


def scenario_amounts_at_spot(
    payload: ForwardStrategyProbabilityRequest,
    spot: float,
) -> ScenarioAmounts:
    scenario_request = ForwardStrategyScenarioRequest(
        **payload.model_dump(),
        assumed_maturity_spot=spot,
    )
    result = calculate_forward_strategy_scenario(scenario_request)
    return ScenarioAmounts(
        result_kind=result.result_kind,
        no_hedge_amount_cny=result.no_hedge_amount_cny,
        strategy_amount_cny=result.strategy_amount_cny,
        coverage=result.coverage,
    )


def calculate_amount_range(
    payload: ForwardStrategyProbabilityRequest,
    distribution: LognormalDistribution,
    *,
    probability: float,
    lower_percentile: float,
    upper_percentile: float,
    strategy: bool,
) -> AmountProbabilityRange:
    lower_spot = distribution.quantile(lower_percentile)
    upper_spot = distribution.quantile(upper_percentile)
    lower_result = scenario_amounts_at_spot(payload, lower_spot)
    upper_result = scenario_amounts_at_spot(payload, upper_spot)
    values = (
        [
            lower_result.strategy_amount_cny,
            upper_result.strategy_amount_cny,
        ]
        if strategy
        else [
            lower_result.no_hedge_amount_cny,
            upper_result.no_hedge_amount_cny,
        ]
    )
    return AmountProbabilityRange(
        probability=probability,
        minimum_amount_cny=min(values),
        maximum_amount_cny=max(values),
    )


def _target_probability(
    *,
    target_cny: float | None,
    intercept: float,
    slope: float,
    exposure_type: ExposureType,
    distribution: LognormalDistribution,
) -> ForwardTargetProbability | None:
    if target_cny is None:
        return None
    normalized_target = cny_amount(Decimal(str(target_cny)))
    if slope == 0:
        normalized_amount = cny_amount(Decimal(str(intercept)))
        met = (
            normalized_amount <= normalized_target
            if exposure_type is ExposureType.USD_PAYABLE
            else normalized_amount >= normalized_target
        )
        probability_met = 1.0 if met else 0.0
        critical_spot = None
    else:
        critical_spot = (float(normalized_target) - intercept) / slope
        probability_below = distribution.cdf(critical_spot)
        amount_condition_is_below = (
            exposure_type is ExposureType.USD_PAYABLE
        )
        spot_condition_is_below = (
            amount_condition_is_below
            if slope > 0
            else not amount_condition_is_below
        )
        probability_met = (
            probability_below
            if spot_condition_is_below
            else 1.0 - probability_below
        )
    probability_met = min(1.0, max(0.0, probability_met))
    return ForwardTargetProbability(
        target_cny=float(normalized_target),
        critical_spot=critical_spot,
        probability_met=probability_met,
        probability_missed=1.0 - probability_met,
    )


def _strategy_better_probability(
    *,
    break_even_spot: float,
    exposure_type: ExposureType,
    distribution: LognormalDistribution,
) -> float:
    probability_below = distribution.cdf(break_even_spot)
    if exposure_type is ExposureType.USD_PAYABLE:
        return 1.0 - probability_below
    return probability_below


def _range_width_comparison(
    no_hedge: AmountProbabilityRange,
    strategy: AmountProbabilityRange,
) -> RangeWidthComparison:
    no_hedge_width = cny_amount(
        Decimal(str(no_hedge.maximum_amount_cny))
        - Decimal(str(no_hedge.minimum_amount_cny))
    )
    strategy_width = cny_amount(
        Decimal(str(strategy.maximum_amount_cny))
        - Decimal(str(strategy.minimum_amount_cny))
    )
    difference = strategy_width - no_hedge_width
    change = (
        RangeChange.REDUCED
        if difference < 0
        else RangeChange.INCREASED
        if difference > 0
        else RangeChange.UNCHANGED
    )
    return RangeWidthComparison(
        no_hedge_width_cny=float(no_hedge_width),
        strategy_width_cny=float(strategy_width),
        strategy_minus_no_hedge_cny=float(difference),
        change=change,
    )


def _spot_range(
    distribution: LognormalDistribution,
    *,
    probability: float,
    lower_percentile: float,
    upper_percentile: float,
) -> SpotProbabilityRange:
    return SpotProbabilityRange(
        probability=probability,
        lower_spot=distribution.quantile(lower_percentile),
        upper_spot=distribution.quantile(upper_percentile),
    )


def calculate_forward_strategy_probability(
    payload: ForwardStrategyProbabilityRequest,
    *,
    expected_maturity_spot: float,
    annualized_volatility_pct: float,
    valuation_date: date | None = None,
    source_type: Literal["assumption", "market_data"] = "assumption",
    is_market_forecast: bool = False,
) -> ForwardStrategyProbabilityResponse:
    distribution = build_lognormal_distribution(
        expected_spot=expected_maturity_spot,
        annualized_volatility_pct=annualized_volatility_pct,
        maturity_date=payload.maturity_date,
        valuation_date=valuation_date,
    )
    expected = scenario_amounts_at_spot(payload, expected_maturity_spot)
    typical_spot = _spot_range(
        distribution,
        probability=0.50,
        lower_percentile=0.25,
        upper_percentile=0.75,
    )
    wide_spot = _spot_range(
        distribution,
        probability=0.90,
        lower_percentile=0.05,
        upper_percentile=0.95,
    )
    no_hedge_typical = calculate_amount_range(
        payload,
        distribution,
        probability=0.50,
        lower_percentile=0.25,
        upper_percentile=0.75,
        strategy=False,
    )
    no_hedge_wide = calculate_amount_range(
        payload,
        distribution,
        probability=0.90,
        lower_percentile=0.05,
        upper_percentile=0.95,
        strategy=False,
    )
    strategy_typical = calculate_amount_range(
        payload,
        distribution,
        probability=0.50,
        lower_percentile=0.25,
        upper_percentile=0.75,
        strategy=True,
    )
    strategy_wide = calculate_amount_range(
        payload,
        distribution,
        probability=0.90,
        lower_percentile=0.05,
        upper_percentile=0.95,
        strategy=True,
    )

    exposure = Decimal(str(payload.notional_usd))
    total_forward = sum(
        (Decimal(str(leg.notional_usd)) for leg in payload.forward_legs),
        Decimal("0"),
    )
    locked_cny = sum(
        (
            Decimal(str(leg.notional_usd))
            * Decimal(str(leg.forward_rate))
            for leg in payload.forward_legs
        ),
        Decimal("0"),
    )
    break_even_spot = float(locked_cny / total_forward)
    probability_strategy_better = _strategy_better_probability(
        break_even_spot=break_even_spot,
        exposure_type=payload.exposure_type,
        distribution=distribution,
    )

    return ForwardStrategyProbabilityResponse(
        result_kind=expected.result_kind,
        distribution=ForwardProbabilityDistribution(
            source_type=source_type,
            is_market_forecast=is_market_forecast,
            assumed_expected_maturity_spot=expected_maturity_spot,
            assumed_annualized_volatility_pct=annualized_volatility_pct,
            horizon_days=distribution.horizon_days,
            typical_spot_range_50=typical_spot,
            wide_spot_range_90=wide_spot,
        ),
        no_hedge=StrategyProbabilityResult(
            expected_amount_cny=expected.no_hedge_amount_cny,
            typical_range_50=no_hedge_typical,
            wide_range_90=no_hedge_wide,
            target_probability=_target_probability(
                target_cny=payload.target_cny,
                intercept=0.0,
                slope=float(exposure),
                exposure_type=payload.exposure_type,
                distribution=distribution,
            ),
        ),
        forward_strategy=ForwardStrategyProbabilityResult(
            expected_amount_cny=expected.strategy_amount_cny,
            typical_range_50=strategy_typical,
            wide_range_90=strategy_wide,
            target_probability=_target_probability(
                target_cny=payload.target_cny,
                intercept=float(locked_cny),
                slope=float(exposure - total_forward),
                exposure_type=payload.exposure_type,
                distribution=distribution,
            ),
            coverage=expected.coverage,
        ),
        comparison=ForwardStrategyProbabilityComparison(
            break_even_spot=break_even_spot,
            probability_strategy_better=probability_strategy_better,
            probability_no_hedge_better=(
                1.0 - probability_strategy_better
            ),
            wide_range_90_width=_range_width_comparison(
                no_hedge_wide,
                strategy_wide,
            ),
        ),
    )
