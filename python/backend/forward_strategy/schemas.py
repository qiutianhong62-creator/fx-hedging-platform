from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from backend.models import (
    AnalysisInput,
    DistributionMetadata,
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


class ForwardStrategyProbabilityRequest(AnalysisInput):
    notional_usd: PositiveFinite
    target_cny: Annotated[
        float | None,
        Field(gt=0, allow_inf_nan=False),
    ] = None
    forward_legs: Annotated[
        list[ForwardLegInput],
        Field(min_length=1),
    ]


class RangeChange(str, Enum):
    REDUCED = "reduced"
    UNCHANGED = "unchanged"
    INCREASED = "increased"


class SpotProbabilityRange(BaseModel):
    probability: float
    lower_spot: float
    upper_spot: float


class AmountProbabilityRange(BaseModel):
    probability: float
    minimum_amount_cny: float
    maximum_amount_cny: float


class ForwardProbabilityDistribution(DistributionMetadata):
    typical_spot_range_50: SpotProbabilityRange
    wide_spot_range_90: SpotProbabilityRange


class ForwardTargetProbability(BaseModel):
    target_cny: float
    critical_spot: float | None
    probability_met: float
    probability_missed: float


class StrategyProbabilityResult(BaseModel):
    expected_amount_cny: float
    typical_range_50: AmountProbabilityRange
    wide_range_90: AmountProbabilityRange
    target_probability: ForwardTargetProbability | None


class ForwardStrategyProbabilityResult(StrategyProbabilityResult):
    coverage: ForwardCoverage


class RangeWidthComparison(BaseModel):
    no_hedge_width_cny: float
    strategy_width_cny: float
    strategy_minus_no_hedge_cny: float
    change: RangeChange


class ForwardStrategyProbabilityComparison(BaseModel):
    break_even_spot: float
    probability_strategy_better: float
    probability_no_hedge_better: float
    wide_range_90_width: RangeWidthComparison


class ProfileAmountRange(BaseModel):
    minimum_amount_cny: float
    maximum_amount_cny: float


class ForwardProbabilityProfileInterval(BaseModel):
    lower_spot: float
    upper_spot: float
    interval_probability: float
    probability_below_upper: float
    probability_above_upper: float
    no_hedge: ProfileAmountRange
    forward_strategy: ProfileAmountRange


class ForwardProbabilityProfileTail(BaseModel):
    direction: Literal["below", "above"]
    boundary_spot: float
    probability: float
    no_hedge_amount_cny: float
    forward_strategy_amount_cny: float


class ForwardProbabilityProfile(BaseModel):
    core_lower_spot: float
    core_upper_spot: float
    core_probability: float
    bucket_count: int
    intervals: list[ForwardProbabilityProfileInterval]
    lower_tail: ForwardProbabilityProfileTail
    upper_tail: ForwardProbabilityProfileTail


class ForwardStrategyProbabilityResponse(BaseModel):
    status: Literal["calculated"] = "calculated"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    result_kind: ResultKind
    distribution: ForwardProbabilityDistribution
    no_hedge: StrategyProbabilityResult
    forward_strategy: ForwardStrategyProbabilityResult
    comparison: ForwardStrategyProbabilityComparison
    probability_profile: ForwardProbabilityProfile
