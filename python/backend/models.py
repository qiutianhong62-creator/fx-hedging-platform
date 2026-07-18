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
