from dataclasses import dataclass

from backend.forward_strategy.schemas import (
    AmountProbabilityRange,
    ForwardCoverage,
    ForwardStrategyProbabilityRequest,
    ForwardStrategyScenarioRequest,
)
from backend.forward_strategy.service import (
    calculate_forward_strategy_scenario,
)
from backend.models import ResultKind
from backend.services.distributions import LognormalDistribution


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
