from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class ExposureType(str, Enum):
    USD_RECEIVABLE = "usd_receivable"
    USD_PAYABLE = "usd_payable"
    USD_HOLDING = "usd_holding"


class AnalysisInput(BaseModel):
    currency_pair: Literal["USD/CNY"] = "USD/CNY"
    exposure_type: ExposureType
    notional_usd: Annotated[float, Field(gt=0)]
    maturity_date: date
    target_cny: Annotated[float | None, Field(gt=0)] = None

    @field_validator("maturity_date")
    @classmethod
    def maturity_must_be_in_the_future(cls, value: date) -> date:
        if value <= date.today():
            raise ValueError("到期日必须晚于今天")
        return value


class ValidationResponse(BaseModel):
    status: Literal["valid"] = "valid"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    normalized_input: AnalysisInput


class ResultKind(str, Enum):
    CNY_PROCEEDS = "cny_proceeds"
    CNY_COST = "cny_cost"


class DifferenceType(str, Enum):
    ON_TARGET = "on_target"
    SURPLUS = "surplus"
    SHORTFALL = "shortfall"
    COST_SAVING = "cost_saving"
    EXCESS_COST = "excess_cost"


class NoHedgeScenarioRequest(AnalysisInput):
    assumed_maturity_spot: Annotated[float, Field(gt=0)]


class ScenarioMetadata(BaseModel):
    scenario_type: Literal["assumption"] = "assumption"
    is_forecast: Literal[False] = False
    assumed_maturity_spot: float


class TargetComparison(BaseModel):
    target_cny: float
    target_met: bool
    difference_cny: float
    difference_type: DifferenceType


class NoHedgeScenarioResponse(BaseModel):
    status: Literal["calculated"] = "calculated"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    scenario: ScenarioMetadata
    result_kind: ResultKind
    no_hedge_amount_cny: float
    target_comparison: TargetComparison | None


class NoHedgeProbabilityRequest(AnalysisInput):
    assumed_expected_maturity_spot: Annotated[
        float,
        Field(gt=0, allow_inf_nan=False),
    ]
    assumed_annualized_volatility_pct: Annotated[
        float,
        Field(gt=0, allow_inf_nan=False),
    ]


class DistributionMetadata(BaseModel):
    model_type: Literal["lognormal"] = "lognormal"
    source_type: Literal["assumption", "market_data"] = "assumption"
    is_market_forecast: bool = False
    assumed_expected_maturity_spot: float
    assumed_annualized_volatility_pct: float
    horizon_days: int


class ExpectedResult(BaseModel):
    spot: float
    amount_cny: float


class ProbabilityRange(BaseModel):
    probability: float
    lower_spot: float
    upper_spot: float
    lower_amount_cny: float
    upper_amount_cny: float


class TargetProbability(BaseModel):
    target_cny: float
    critical_spot: float
    probability_met: float
    probability_missed: float


class NoHedgeProbabilityResponse(BaseModel):
    status: Literal["calculated"] = "calculated"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    distribution: DistributionMetadata
    result_kind: ResultKind
    expected_result: ExpectedResult
    typical_range_50: ProbabilityRange
    wide_range_90: ProbabilityRange
    target_probability: TargetProbability | None
