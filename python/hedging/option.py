from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class OptionPosition(str, Enum):
    BUY = "buy"
    SELL = "sell"


class ExposureDirection(str, Enum):
    RECEIVABLE = "receivable"
    PAYABLE = "payable"


@dataclass(frozen=True)
class OptionInputs:
    notional_usd: float
    option_type: OptionType
    position: OptionPosition
    strike_rate: float
    premium_rate_cny_per_usd: float
    maturity_spot: float
    exposure_direction: ExposureDirection

    def validate(self) -> None:
        if self.notional_usd < 0:
            raise ValueError("期权名义金额必须是非负数")
        if self.strike_rate <= 0:
            raise ValueError("期权执行价必须大于零")
        if self.premium_rate_cny_per_usd < 0:
            raise ValueError("期权费率必须是非负数")
        if self.maturity_spot <= 0:
            raise ValueError("到期即期汇率必须大于零")


@dataclass(frozen=True)
class OptionResult:
    intrinsic_value_cny: float
    gross_option_payoff_cny: float
    premium_cashflow_cny: float
    net_option_cashflow_cny: float
    baseline_cashflow_cny: float
    final_cashflow_cny: float
    hedging_effect_cny: float
    break_even_rate: float


@dataclass(frozen=True)
class OptionScenarioPoint:
    spot: float
    baseline_cashflow_cny: float
    final_cashflow_cny: float
    net_option_cashflow_cny: float


class CurrencyOption:
    product_id = "option"
    name = "外汇期权"

    def __init__(self, inputs: OptionInputs):
        inputs.validate()
        self.inputs = inputs

    def calculate(self) -> OptionResult:
        inputs = self.inputs
        if inputs.option_type is OptionType.CALL:
            unit_intrinsic = max(inputs.maturity_spot - inputs.strike_rate, 0)
            break_even_rate = inputs.strike_rate + inputs.premium_rate_cny_per_usd
        else:
            unit_intrinsic = max(inputs.strike_rate - inputs.maturity_spot, 0)
            break_even_rate = inputs.strike_rate - inputs.premium_rate_cny_per_usd

        intrinsic_value_cny = unit_intrinsic * inputs.notional_usd
        position_sign = 1 if inputs.position is OptionPosition.BUY else -1
        gross_option_payoff_cny = position_sign * intrinsic_value_cny
        premium_cny = inputs.premium_rate_cny_per_usd * inputs.notional_usd
        premium_cashflow_cny = (
            -premium_cny if inputs.position is OptionPosition.BUY else premium_cny
        )
        net_option_cashflow_cny = gross_option_payoff_cny + premium_cashflow_cny
        baseline_cashflow_cny = inputs.notional_usd * inputs.maturity_spot
        if inputs.exposure_direction is ExposureDirection.RECEIVABLE:
            final_cashflow_cny = baseline_cashflow_cny + net_option_cashflow_cny
        else:
            final_cashflow_cny = baseline_cashflow_cny - net_option_cashflow_cny

        return OptionResult(
            intrinsic_value_cny=intrinsic_value_cny,
            gross_option_payoff_cny=gross_option_payoff_cny,
            premium_cashflow_cny=premium_cashflow_cny,
            net_option_cashflow_cny=net_option_cashflow_cny,
            baseline_cashflow_cny=baseline_cashflow_cny,
            final_cashflow_cny=final_cashflow_cny,
            hedging_effect_cny=net_option_cashflow_cny,
            break_even_rate=break_even_rate,
        )

    def scenario_curve(
        self, minimum_spot: float, maximum_spot: float, steps: int = 31
    ) -> list[OptionScenarioPoint]:
        if steps < 2:
            raise ValueError("情景数量至少为2")
        interval = (maximum_spot - minimum_spot) / (steps - 1)
        points: list[OptionScenarioPoint] = []
        for index in range(steps):
            spot = minimum_spot + interval * index
            result = CurrencyOption(
                replace(self.inputs, maturity_spot=spot)
            ).calculate()
            points.append(
                OptionScenarioPoint(
                    spot=spot,
                    baseline_cashflow_cny=result.baseline_cashflow_cny,
                    final_cashflow_cny=result.final_cashflow_cny,
                    net_option_cashflow_cny=result.net_option_cashflow_cny,
                )
            )
        return points

    def risk_description(self) -> str:
        inputs = self.inputs
        if inputs.position is OptionPosition.BUY:
            return "期权买方拥有行权权利，最大期权头寸损失为已支付的期权费。"
        if inputs.option_type is OptionType.CALL:
            return "卖出看涨期权收取期权费，但汇率持续上涨时可能产生很大的履约损失。"
        return "卖出看跌期权收取期权费，但汇率大幅下跌时可能产生显著履约损失。"
