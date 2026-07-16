from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


class StrategyLeg(Protocol):
    product_id: str
    name: str
    allocation_ratio: float

    def income_cny(self, exposure_usd: float, maturity_spot: float) -> float: ...

    @property
    def upfront_cost_cny(self) -> float: ...


@dataclass(frozen=True)
class ForwardLeg:
    allocation_ratio: float
    forward_rate: float
    product_id: str = "forward"
    name: str = "远期结汇"

    def income_cny(self, exposure_usd: float, maturity_spot: float) -> float:
        del maturity_spot
        return exposure_usd * self.allocation_ratio * self.forward_rate

    @property
    def upfront_cost_cny(self) -> float:
        return 0.0


@dataclass(frozen=True)
class CompositeResult:
    covered_ratio: float
    uncovered_ratio: float
    covered_usd: float
    uncovered_usd: float
    product_income_cny: float
    uncovered_income_cny: float
    total_income_cny: float
    baseline_income_cny: float
    difference_cny: float
    upfront_cost_cny: float


@dataclass(frozen=True)
class CompositeScenarioPoint:
    spot: float
    income_cny: float
    difference_cny: float


class CompositeStrategy:
    """由多个产品组成项汇总而成的套保策略。"""

    def __init__(self, name: str, legs: Sequence[StrategyLeg]):
        self.name = name
        self.legs = tuple(legs)
        self._validate()

    def _validate(self) -> None:
        covered_ratio = 0.0
        for leg in self.legs:
            if leg.allocation_ratio < 0:
                raise ValueError(f"{leg.name}的配置比例必须是非负数")
            if isinstance(leg, ForwardLeg) and leg.forward_rate <= 0:
                raise ValueError("远期汇率必须大于零")
            covered_ratio += leg.allocation_ratio
        if covered_ratio > 1 + 1e-9:
            raise ValueError("组合策略总覆盖比例超过100%，存在重复或过度套保")

    def calculate(self, exposure_usd: float, maturity_spot: float) -> CompositeResult:
        if exposure_usd < 0:
            raise ValueError("美元敞口必须是非负数")
        if maturity_spot <= 0:
            raise ValueError("到期即期汇率必须大于零")

        covered_ratio = min(1.0, sum(leg.allocation_ratio for leg in self.legs))
        uncovered_ratio = max(0.0, 1 - covered_ratio)
        product_income_cny = sum(
            leg.income_cny(exposure_usd, maturity_spot) for leg in self.legs
        )
        upfront_cost_cny = sum(leg.upfront_cost_cny for leg in self.legs)
        uncovered_usd = exposure_usd * uncovered_ratio
        uncovered_income_cny = uncovered_usd * maturity_spot
        total_income_cny = (
            product_income_cny + uncovered_income_cny - upfront_cost_cny
        )
        baseline_income_cny = exposure_usd * maturity_spot
        return CompositeResult(
            covered_ratio=covered_ratio,
            uncovered_ratio=uncovered_ratio,
            covered_usd=exposure_usd * covered_ratio,
            uncovered_usd=uncovered_usd,
            product_income_cny=product_income_cny,
            uncovered_income_cny=uncovered_income_cny,
            total_income_cny=total_income_cny,
            baseline_income_cny=baseline_income_cny,
            difference_cny=total_income_cny - baseline_income_cny,
            upfront_cost_cny=upfront_cost_cny,
        )

    def scenario_curve(
        self,
        exposure_usd: float,
        minimum_spot: float,
        maximum_spot: float,
        steps: int = 21,
    ) -> list[CompositeScenarioPoint]:
        if steps < 2:
            raise ValueError("情景数量至少为2")
        interval = (maximum_spot - minimum_spot) / (steps - 1)
        points: list[CompositeScenarioPoint] = []
        for index in range(steps):
            spot = minimum_spot + interval * index
            result = self.calculate(exposure_usd, spot)
            points.append(
                CompositeScenarioPoint(
                    spot=spot,
                    income_cny=result.total_income_cny,
                    difference_cny=result.difference_cny,
                )
            )
        return points
