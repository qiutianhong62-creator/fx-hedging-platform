from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from backend.models import (
    AnalysisInput,
    ResultKind,
    TargetComparison,
)


PositiveFinite = Annotated[
    float,
    Field(gt=0, allow_inf_nan=False),
]


class ForwardDirection(str, Enum):
    SELL_USD = "sell_usd"
    BUY_USD = "buy_usd"


class EconomicEffect(str, Enum):
    IMPROVEMENT = "improvement"
    WORSENING = "worsening"
    NO_CHANGE = "no_change"


class CoverageStatus(str, Enum):
    PARTIAL_HEDGE = "partial_hedge"
    FULL_HEDGE = "full_hedge"
    OVER_HEDGED = "over_hedged"


class ForwardLegInput(BaseModel):
    notional_usd: PositiveFinite
    forward_rate: PositiveFinite


class ForwardStrategyScenarioRequest(AnalysisInput):
    notional_usd: PositiveFinite
    target_cny: Annotated[
        float | None,
        Field(gt=0, allow_inf_nan=False),
    ] = None
    assumed_maturity_spot: PositiveFinite
    forward_legs: Annotated[
        list[ForwardLegInput],
        Field(min_length=1),
    ]


class ForwardScenarioMetadata(BaseModel):
    scenario_type: Literal["assumption"] = "assumption"
    is_forecast: Literal[False] = False
    assumed_maturity_spot: float
    forward_direction: ForwardDirection


class ForwardLegResult(BaseModel):
    leg_index: int
    direction: ForwardDirection
    notional_usd: float
    forward_rate: float
    difference_cny: float
    economic_effect: EconomicEffect


class ForwardWarning(BaseModel):
    code: Literal["over_hedged"] = "over_hedged"
    message: str


class ForwardCoverage(BaseModel):
    total_forward_notional_usd: float
    coverage_ratio: float
    unhedged_notional_usd: float
    overhedged_notional_usd: float
    status: CoverageStatus
    warnings: list[ForwardWarning]


class ForwardTargetComparison(BaseModel):
    no_hedge: TargetComparison
    strategy: TargetComparison


class ForwardStrategyScenarioResponse(BaseModel):
    status: Literal["calculated"] = "calculated"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    scenario: ForwardScenarioMetadata
    result_kind: ResultKind
    no_hedge_amount_cny: float
    strategy_amount_cny: float
    strategy_minus_no_hedge_cny: float
    economic_effect: EconomicEffect
    forward_legs: list[ForwardLegResult]
    coverage: ForwardCoverage
    target_comparison: ForwardTargetComparison | None
