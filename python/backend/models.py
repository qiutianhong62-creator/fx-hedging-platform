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
