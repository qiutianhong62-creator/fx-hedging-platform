from __future__ import annotations

from typing import Protocol, Sequence


class HedgeProduct(Protocol):
    """所有套保产品遵循的统一接口。"""

    product_id: str
    name: str

    def calculate(self): ...

    def scenario_curve(
        self, minimum_spot: float, maximum_spot: float, steps: int = 15
    ) -> Sequence[object]: ...
