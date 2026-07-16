from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ForwardInputs:
    exposure_usd: float
    hedge_ratio: float
    forward_rate: float
    maturity_spot: float

    def validate(self) -> None:
        if self.exposure_usd < 0:
            raise ValueError("美元敞口必须是非负数")
        if not 0 <= self.hedge_ratio <= 1:
            raise ValueError("套保比例必须位于0%至100%之间")
        if self.forward_rate <= 0 or self.maturity_spot <= 0:
            raise ValueError("汇率必须大于零")


@dataclass(frozen=True)
class ForwardResult:
    hedged_usd: float
    unhedged_usd: float
    total_income_cny: float
    unhedged_income_cny: float
    difference_cny: float


@dataclass(frozen=True)
class ScenarioPoint:
    spot: float
    hedged_income_cny: float
    unhedged_income_cny: float
    difference_cny: float


class ForwardHedge:
    product_id = "forward"
    name = "远期结汇"

    def __init__(self, inputs: ForwardInputs):
        inputs.validate()
        self.inputs = inputs

    def calculate(self) -> ForwardResult:
        inputs = self.inputs
        hedged_usd = inputs.exposure_usd * inputs.hedge_ratio
        unhedged_usd = inputs.exposure_usd - hedged_usd
        total_income_cny = (
            hedged_usd * inputs.forward_rate
            + unhedged_usd * inputs.maturity_spot
        )
        unhedged_income_cny = inputs.exposure_usd * inputs.maturity_spot
        return ForwardResult(
            hedged_usd=hedged_usd,
            unhedged_usd=unhedged_usd,
            total_income_cny=total_income_cny,
            unhedged_income_cny=unhedged_income_cny,
            difference_cny=total_income_cny - unhedged_income_cny,
        )

    def scenario_curve(
        self, minimum_spot: float, maximum_spot: float, steps: int = 15
    ) -> list[ScenarioPoint]:
        if steps < 2:
            raise ValueError("情景数量至少为2")
        interval = (maximum_spot - minimum_spot) / (steps - 1)
        points: list[ScenarioPoint] = []
        for index in range(steps):
            spot = minimum_spot + interval * index
            result = ForwardHedge(
                replace(self.inputs, maturity_spot=spot)
            ).calculate()
            points.append(
                ScenarioPoint(
                    spot=spot,
                    hedged_income_cny=result.total_income_cny,
                    unhedged_income_cny=result.unhedged_income_cny,
                    difference_cny=result.difference_cny,
                )
            )
        return points
