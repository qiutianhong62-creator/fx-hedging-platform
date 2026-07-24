# 第七阶段：多笔远期策略固定汇率情景实施计划

> **给执行者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐步实施。步骤使用复选框（`- [ ]`）跟踪。

**目标：** 新增一个独立接口，在人工假设到期汇率下计算一笔或多笔远期的最终人民币金额、逐笔贡献、覆盖状态、超额套保风险及目标比较。

**架构：** 保留现有不套保接口不变。先提取可复用的金额和目标比较规则，再建立独立的远期请求/响应模型和纯计算器，最后通过单独路由开放接口；本阶段不调用 ING、FRED 或概率模型。

**技术：** Python 3.12、FastAPI、Pydantic 2、`Decimal`、pytest、FastAPI `TestClient`。

## 全局约束

- 货币对仅支持 `USD/CNY`，报价方向固定为 `CNY per 1 USD`。
- 新接口为 `POST /api/v1/analysis/forward-strategy/scenario`。
- 原 `POST /api/v1/analysis/no-hedge/scenario` 的输入和输出保持不变。
- 请求至少包含一笔远期，每笔只填写正且有限的美元名义金额和远期汇率。
- 敞口金额、目标金额和假设到期汇率在新接口中也必须是正且有限的数。
- 所有远期共享敞口的统一到期日；每笔不重复填写到期日、币种或方向。
- 美元应收和持有美元自动使用 `sell_usd`；美元应付自动使用 `buy_usd`。
- 远期合计金额可以超过敞口；不拒绝计算，但必须返回 `over_hedged` 提示。
- 超额卖出美元假设到期按即期买入缺口后履约；超额买入美元假设到期按即期卖出多余美元。
- 人民币结果按现有规则使用 `ROUND_HALF_UP` 保留两位；中间值不提前四舍五入。
- `coverage_ratio` 返回小数，例如 `0.5` 代表 50%。
- 收入增加或成本降低才是 `improvement`；收入减少或成本增加是 `worsening`。
- 本阶段无外部网络、概率、期权、市场参考价、费用、保证金、授信、提前平仓或不同到期日。
- 不修改旧的 `python/hedging/` 原型；其“仅应收、比例输入、禁止超额套保”规则与本阶段已确认需求不同。

---

## 文件分工

- 新建 `python/backend/services/scenario_common.py`：共享人民币舍入和目标比较规则。
- 修改 `python/backend/services/no_hedge.py`：改用共享规则，行为保持不变。
- 新建 `python/backend/forward_strategy/__init__.py`：远期策略模块标记。
- 新建 `python/backend/forward_strategy/schemas.py`：输入、输出、枚举及风险提示模型。
- 新建 `python/backend/forward_strategy/service.py`：多笔远期纯计算器。
- 新建 `python/backend/routes/forward_strategy.py`：独立远期策略接口。
- 修改 `python/backend/main.py`：注册远期策略路由。
- 修改 `python/backend/errors.py`：补充新字段的中文输入错误。
- 新建相应的模型、计算器和 API 测试。

---

### 任务 1：提取共享金额与目标比较规则

**文件：**

- 新建：`python/backend/services/scenario_common.py`
- 修改：`python/backend/services/no_hedge.py`
- 新建：`python/tests/backend/test_scenario_common.py`

**接口：**

- 输入：`Decimal` 人民币金额、`ExposureType`、可选目标金额。
- 输出：`decimal_value(value) -> Decimal`、`cny_amount(value) -> Decimal`、`compare_target(...) -> TargetComparison | None`。

- [ ] **步骤 1：先写共享规则的失败测试**

新建 `python/tests/backend/test_scenario_common.py`：

```python
from decimal import Decimal

from backend.models import DifferenceType, ExposureType
from backend.services.scenario_common import cny_amount, compare_target


def test_cny_amount_uses_half_up_rounding() -> None:
    assert cny_amount(Decimal("1.005")) == Decimal("1.01")


def test_compare_target_treats_lower_payable_cost_as_saving() -> None:
    result = compare_target(
        exposure_type=ExposureType.USD_PAYABLE,
        amount_cny=Decimal("6700000.00"),
        target_cny=6_800_000,
    )

    assert result is not None
    assert result.target_met is True
    assert result.difference_cny == 100_000
    assert result.difference_type is DifferenceType.COST_SAVING


def test_compare_target_returns_none_without_target() -> None:
    assert compare_target(
        exposure_type=ExposureType.USD_RECEIVABLE,
        amount_cny=Decimal("6700000.00"),
        target_cny=None,
    ) is None
```

- [ ] **步骤 2：运行测试，确认共享模块尚不存在**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_scenario_common.py -v
```

预期：测试收集失败，因为 `backend.services.scenario_common` 尚不存在。

- [ ] **步骤 3：建立共享规则**

新建 `python/backend/services/scenario_common.py`：

```python
from decimal import Decimal, ROUND_HALF_UP

from backend.models import (
    DifferenceType,
    ExposureType,
    TargetComparison,
)


CNY_CENT = Decimal("0.01")


def decimal_value(value: float) -> Decimal:
    return Decimal(str(value))


def cny_amount(value: Decimal) -> Decimal:
    return value.quantize(CNY_CENT, rounding=ROUND_HALF_UP)


def compare_target(
    *,
    exposure_type: ExposureType,
    amount_cny: Decimal,
    target_cny: float | None,
) -> TargetComparison | None:
    if target_cny is None:
        return None

    target = cny_amount(decimal_value(target_cny))
    if amount_cny == target:
        return TargetComparison(
            target_cny=float(target),
            target_met=True,
            difference_cny=0.0,
            difference_type=DifferenceType.ON_TARGET,
        )

    if exposure_type is ExposureType.USD_PAYABLE:
        target_met = amount_cny < target
        difference_type = (
            DifferenceType.COST_SAVING
            if target_met
            else DifferenceType.EXCESS_COST
        )
    else:
        target_met = amount_cny > target
        difference_type = (
            DifferenceType.SURPLUS
            if target_met
            else DifferenceType.SHORTFALL
        )

    return TargetComparison(
        target_cny=float(target),
        target_met=target_met,
        difference_cny=float(abs(amount_cny - target)),
        difference_type=difference_type,
    )
```

- [ ] **步骤 4：让现有不套保计算器复用共享规则**

在 `python/backend/services/no_hedge.py`：

- 删除本文件的 `ROUND_HALF_UP`、`CNY_CENT`、`_decimal`、`_cny` 和 `_target_comparison`；
- 保留 `Decimal` 导入；
- 增加：

```python
from backend.services.scenario_common import (
    cny_amount,
    compare_target,
    decimal_value,
)
```

将金额计算替换为：

```python
    amount_cny = cny_amount(
        decimal_value(payload.notional_usd)
        * decimal_value(payload.assumed_maturity_spot)
    )
```

将目标比较替换为：

```python
        target_comparison=compare_target(
            exposure_type=payload.exposure_type,
            amount_cny=amount_cny,
            target_cny=payload.target_cny,
        ),
```

- [ ] **步骤 5：运行共享规则和原不套保测试**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_scenario_common.py tests/backend/test_no_hedge_service.py tests/backend/test_no_hedge_api.py -v
```

预期：新共享规则测试通过，原不套保服务和接口结果不变。

- [ ] **步骤 6：保存共享规则**

```bash
git add python/backend/services/scenario_common.py python/backend/services/no_hedge.py python/tests/backend/test_scenario_common.py
git commit -m "refactor: share scenario amount rules"
```

---

### 任务 2：定义远期策略输入和输出

**文件：**

- 新建：`python/backend/forward_strategy/__init__.py`
- 新建：`python/backend/forward_strategy/schemas.py`
- 新建：`python/tests/backend/test_forward_strategy_models.py`

**接口：**

- 输入：基础敞口、假设到期汇率和至少一笔 `ForwardLegInput`。
- 输出：`ForwardStrategyScenarioRequest`、`ForwardStrategyScenarioResponse` 及所有明细模型和枚举。

- [ ] **步骤 1：先写输入模型失败测试**

新建 `python/tests/backend/test_forward_strategy_models.py`：

```python
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.forward_strategy.schemas import (
    ForwardDirection,
    ForwardStrategyScenarioRequest,
)


def valid_request(**updates) -> dict[str, object]:
    payload: dict[str, object] = {
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": date.today() + timedelta(days=180),
        "target_cny": 6_680_000,
        "assumed_maturity_spot": 6.60,
        "forward_legs": [
            {"notional_usd": 300_000, "forward_rate": 6.80},
            {"notional_usd": 200_000, "forward_rate": 6.75},
        ],
    }
    payload.update(updates)
    return payload


def test_request_accepts_multiple_forward_legs() -> None:
    request = ForwardStrategyScenarioRequest(**valid_request())

    assert len(request.forward_legs) == 2
    assert request.forward_legs[0].notional_usd == 300_000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("notional_usd", float("inf")),
        ("target_cny", float("inf")),
        ("assumed_maturity_spot", float("inf")),
    ],
)
def test_request_rejects_non_finite_top_level_values(
    field: str,
    value: float,
) -> None:
    with pytest.raises(ValidationError):
        ForwardStrategyScenarioRequest(**valid_request(**{field: value}))


def test_request_requires_at_least_one_forward_leg() -> None:
    with pytest.raises(ValidationError):
        ForwardStrategyScenarioRequest(**valid_request(forward_legs=[]))


@pytest.mark.parametrize(
    "leg",
    [
        {"notional_usd": 0, "forward_rate": 6.80},
        {"notional_usd": float("inf"), "forward_rate": 6.80},
        {"notional_usd": 300_000, "forward_rate": 0},
        {"notional_usd": 300_000, "forward_rate": float("nan")},
    ],
)
def test_request_rejects_invalid_forward_leg(leg: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        ForwardStrategyScenarioRequest(
            **valid_request(forward_legs=[leg])
        )


def test_direction_enum_uses_explicit_buy_and_sell_values() -> None:
    assert ForwardDirection.SELL_USD == "sell_usd"
    assert ForwardDirection.BUY_USD == "buy_usd"
```

- [ ] **步骤 2：运行测试，确认远期策略模块尚不存在**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_forward_strategy_models.py -v
```

预期：测试收集失败，因为 `backend.forward_strategy` 尚不存在。

- [ ] **步骤 3：定义完整模型**

新建空文件 `python/backend/forward_strategy/__init__.py`。

新建 `python/backend/forward_strategy/schemas.py`：

```python
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
```

- [ ] **步骤 4：运行模型测试**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_forward_strategy_models.py -v
```

预期：多笔远期通过，空列表以及所有非正、无穷和非数字输入被拒绝。

- [ ] **步骤 5：保存远期策略模型**

```bash
git add python/backend/forward_strategy python/tests/backend/test_forward_strategy_models.py
git commit -m "feat: define forward strategy scenario models"
```

---

### 任务 3：实现多笔远期纯计算器

**文件：**

- 新建：`python/backend/forward_strategy/service.py`
- 新建：`python/tests/backend/test_forward_strategy_service.py`

**接口：**

- 输入：`ForwardStrategyScenarioRequest`。
- 输出：`calculate_forward_strategy_scenario(payload) -> ForwardStrategyScenarioResponse`。

- [ ] **步骤 1：先写人工复算和风险诊断失败测试**

新建 `python/tests/backend/test_forward_strategy_service.py`：

```python
from datetime import date, timedelta

import pytest

from backend.forward_strategy.schemas import (
    CoverageStatus,
    EconomicEffect,
    ForwardDirection,
    ForwardStrategyScenarioRequest,
)
from backend.forward_strategy.service import (
    calculate_forward_strategy_scenario,
)


def request(
    *,
    exposure_type: str = "usd_receivable",
    exposure_usd: float = 1_000_000,
    target_cny: float | None = 6_680_000,
    spot: float = 6.60,
    legs: list[dict[str, float]] | None = None,
) -> ForwardStrategyScenarioRequest:
    return ForwardStrategyScenarioRequest(
        exposure_type=exposure_type,
        notional_usd=exposure_usd,
        maturity_date=date.today() + timedelta(days=180),
        target_cny=target_cny,
        assumed_maturity_spot=spot,
        forward_legs=legs or [
            {"notional_usd": 300_000, "forward_rate": 6.80},
            {"notional_usd": 200_000, "forward_rate": 6.75},
        ],
    )


def test_multiple_receivable_forwards_match_manual_calculation() -> None:
    result = calculate_forward_strategy_scenario(request())

    assert result.scenario.forward_direction is ForwardDirection.SELL_USD
    assert result.no_hedge_amount_cny == 6_600_000
    assert result.forward_legs[0].difference_cny == 60_000
    assert result.forward_legs[1].difference_cny == 30_000
    assert result.strategy_amount_cny == 6_690_000
    assert result.strategy_minus_no_hedge_cny == 90_000
    assert result.economic_effect is EconomicEffect.IMPROVEMENT
    assert result.coverage.coverage_ratio == 0.5
    assert result.coverage.unhedged_notional_usd == 500_000
    assert result.coverage.status is CoverageStatus.PARTIAL_HEDGE
    assert result.target_comparison is not None
    assert result.target_comparison.no_hedge.target_met is False
    assert result.target_comparison.strategy.target_met is True


def test_same_positive_difference_worsens_payable_cost() -> None:
    result = calculate_forward_strategy_scenario(
        request(exposure_type="usd_payable")
    )

    assert result.scenario.forward_direction is ForwardDirection.BUY_USD
    assert result.strategy_amount_cny == 6_690_000
    assert result.strategy_minus_no_hedge_cny == 90_000
    assert result.economic_effect is EconomicEffect.WORSENING
    assert all(
        leg.economic_effect is EconomicEffect.WORSENING
        for leg in result.forward_legs
    )


def test_usd_holding_uses_sell_direction_and_proceeds() -> None:
    result = calculate_forward_strategy_scenario(
        request(exposure_type="usd_holding", target_cny=None)
    )

    assert result.scenario.forward_direction is ForwardDirection.SELL_USD
    assert result.result_kind == "cny_proceeds"
    assert result.economic_effect is EconomicEffect.IMPROVEMENT


@pytest.mark.parametrize(
    ("total_notional", "expected_status"),
    [
        (1_000_000, CoverageStatus.FULL_HEDGE),
        (1_200_000, CoverageStatus.OVER_HEDGED),
    ],
)
def test_full_and_over_hedge_status(
    total_notional: float,
    expected_status: CoverageStatus,
) -> None:
    result = calculate_forward_strategy_scenario(
        request(
            target_cny=None,
            legs=[{"notional_usd": total_notional, "forward_rate": 6.80}],
        )
    )

    assert result.coverage.status is expected_status
    assert result.coverage.overhedged_notional_usd == max(
        total_notional - 1_000_000,
        0,
    )
    assert bool(result.coverage.warnings) is (
        expected_status is CoverageStatus.OVER_HEDGED
    )
    if expected_status is CoverageStatus.OVER_HEDGED:
        assert result.coverage.warnings[0].code == "over_hedged"
        assert "额外方向性风险" in result.coverage.warnings[0].message


def test_equal_forward_and_spot_rates_have_no_effect() -> None:
    result = calculate_forward_strategy_scenario(
        request(
            target_cny=None,
            legs=[{"notional_usd": 500_000, "forward_rate": 6.60}],
        )
    )

    assert result.strategy_minus_no_hedge_cny == 0
    assert result.economic_effect is EconomicEffect.NO_CHANGE
    assert result.forward_legs[0].economic_effect is EconomicEffect.NO_CHANGE
    assert result.target_comparison is None


def test_intermediate_values_are_not_rounded_before_sum() -> None:
    result = calculate_forward_strategy_scenario(
        request(
            exposure_usd=1,
            target_cny=None,
            spot=1,
            legs=[
                {"notional_usd": 1, "forward_rate": 1.005},
                {"notional_usd": 1, "forward_rate": 1.005},
            ],
        )
    )

    assert result.strategy_amount_cny == 1.01
```

- [ ] **步骤 2：运行测试，确认计算器尚不存在**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_forward_strategy_service.py -v
```

预期：测试收集失败，因为 `backend.forward_strategy.service` 尚不存在。

- [ ] **步骤 3：实现纯计算器**

新建 `python/backend/forward_strategy/service.py`：

```python
from decimal import Decimal

from backend.forward_strategy.schemas import (
    CoverageStatus,
    EconomicEffect,
    ForwardCoverage,
    ForwardDirection,
    ForwardLegResult,
    ForwardScenarioMetadata,
    ForwardStrategyScenarioRequest,
    ForwardStrategyScenarioResponse,
    ForwardTargetComparison,
    ForwardWarning,
)
from backend.models import ExposureType, ResultKind
from backend.services.scenario_common import (
    cny_amount,
    compare_target,
    decimal_value,
)


OVER_HEDGE_MESSAGE = (
    "远期总金额超过真实美元敞口，超额部分会产生额外方向性风险；"
    "本阶段未计算保证金、授信或额外资金占用。"
)


def _direction(exposure_type: ExposureType) -> ForwardDirection:
    if exposure_type is ExposureType.USD_PAYABLE:
        return ForwardDirection.BUY_USD
    return ForwardDirection.SELL_USD


def _effect(
    exposure_type: ExposureType,
    difference: Decimal,
) -> EconomicEffect:
    if difference == 0:
        return EconomicEffect.NO_CHANGE
    improvement = (
        difference < 0
        if exposure_type is ExposureType.USD_PAYABLE
        else difference > 0
    )
    return (
        EconomicEffect.IMPROVEMENT
        if improvement
        else EconomicEffect.WORSENING
    )


def calculate_forward_strategy_scenario(
    payload: ForwardStrategyScenarioRequest,
) -> ForwardStrategyScenarioResponse:
    exposure = decimal_value(payload.notional_usd)
    spot = decimal_value(payload.assumed_maturity_spot)
    direction = _direction(payload.exposure_type)
    raw_no_hedge = exposure * spot
    no_hedge_amount = cny_amount(raw_no_hedge)

    raw_leg_differences = [
        decimal_value(leg.notional_usd)
        * (decimal_value(leg.forward_rate) - spot)
        for leg in payload.forward_legs
    ]
    strategy_amount = cny_amount(
        raw_no_hedge + sum(raw_leg_differences, Decimal("0"))
    )
    total_difference = strategy_amount - no_hedge_amount
    leg_results = [
        ForwardLegResult(
            leg_index=index,
            direction=direction,
            notional_usd=leg.notional_usd,
            forward_rate=leg.forward_rate,
            difference_cny=float(cny_amount(raw_difference)),
            economic_effect=_effect(
                payload.exposure_type,
                raw_difference,
            ),
        )
        for index, (leg, raw_difference) in enumerate(
            zip(payload.forward_legs, raw_leg_differences, strict=True),
            start=1,
        )
    ]

    total_notional = sum(
        (decimal_value(leg.notional_usd) for leg in payload.forward_legs),
        Decimal("0"),
    )
    unhedged = max(exposure - total_notional, Decimal("0"))
    overhedged = max(total_notional - exposure, Decimal("0"))
    if overhedged > 0:
        status = CoverageStatus.OVER_HEDGED
        warnings = [ForwardWarning(message=OVER_HEDGE_MESSAGE)]
    elif total_notional == exposure:
        status = CoverageStatus.FULL_HEDGE
        warnings = []
    else:
        status = CoverageStatus.PARTIAL_HEDGE
        warnings = []

    target = None
    if payload.target_cny is not None:
        target = ForwardTargetComparison(
            no_hedge=compare_target(
                exposure_type=payload.exposure_type,
                amount_cny=no_hedge_amount,
                target_cny=payload.target_cny,
            ),
            strategy=compare_target(
                exposure_type=payload.exposure_type,
                amount_cny=strategy_amount,
                target_cny=payload.target_cny,
            ),
        )

    result_kind = (
        ResultKind.CNY_COST
        if payload.exposure_type is ExposureType.USD_PAYABLE
        else ResultKind.CNY_PROCEEDS
    )
    return ForwardStrategyScenarioResponse(
        scenario=ForwardScenarioMetadata(
            assumed_maturity_spot=payload.assumed_maturity_spot,
            forward_direction=direction,
        ),
        result_kind=result_kind,
        no_hedge_amount_cny=float(no_hedge_amount),
        strategy_amount_cny=float(strategy_amount),
        strategy_minus_no_hedge_cny=float(total_difference),
        economic_effect=_effect(
            payload.exposure_type,
            total_difference,
        ),
        forward_legs=leg_results,
        coverage=ForwardCoverage(
            total_forward_notional_usd=float(total_notional),
            coverage_ratio=float(total_notional / exposure),
            unhedged_notional_usd=float(unhedged),
            overhedged_notional_usd=float(overhedged),
            status=status,
            warnings=warnings,
        ),
        target_comparison=target,
    )
```

- [ ] **步骤 4：运行远期计算器及不套保回归测试**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_forward_strategy_service.py tests/backend/test_no_hedge_service.py -v
```

预期：所有人工复算、经济方向、覆盖状态、目标和舍入测试通过。

- [ ] **步骤 5：保存远期纯计算器**

```bash
git add python/backend/forward_strategy/service.py python/tests/backend/test_forward_strategy_service.py
git commit -m "feat: calculate multi forward scenarios"
```

---

### 任务 4：开放远期策略 API

**文件：**

- 新建：`python/backend/routes/forward_strategy.py`
- 修改：`python/backend/main.py`
- 修改：`python/backend/errors.py`
- 新建：`python/tests/backend/test_forward_strategy_api.py`

**接口：**

- 输入：`ForwardStrategyScenarioRequest` JSON。
- 输出：`POST /api/v1/analysis/forward-strategy/scenario` 的 `ForwardStrategyScenarioResponse` 或现有统一输入错误。

- [ ] **步骤 1：先写接口成功与错误测试**

新建 `python/tests/backend/test_forward_strategy_api.py`：

```python
from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)
URL = "/api/v1/analysis/forward-strategy/scenario"


def valid_payload() -> dict[str, object]:
    return {
        "currency_pair": "USD/CNY",
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": (date.today() + timedelta(days=180)).isoformat(),
        "target_cny": 6_680_000,
        "assumed_maturity_spot": 6.60,
        "forward_legs": [
            {"notional_usd": 300_000, "forward_rate": 6.80},
            {"notional_usd": 200_000, "forward_rate": 6.75},
        ],
    }


def test_forward_strategy_endpoint_matches_manual_example() -> None:
    response = client.post(URL, json=valid_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "calculated"
    assert body["scenario"]["is_forecast"] is False
    assert body["scenario"]["forward_direction"] == "sell_usd"
    assert body["no_hedge_amount_cny"] == 6_600_000
    assert body["strategy_amount_cny"] == 6_690_000
    assert body["strategy_minus_no_hedge_cny"] == 90_000
    assert body["coverage"]["status"] == "partial_hedge"
    assert body["target_comparison"]["no_hedge"]["target_met"] is False
    assert body["target_comparison"]["strategy"]["target_met"] is True


def test_forward_strategy_endpoint_rejects_empty_legs_friendly() -> None:
    payload = valid_payload()
    payload["forward_legs"] = []

    response = client.post(URL, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["fields"] == [
        {
            "field": "forward_legs",
            "message": "请至少输入一笔远期交易",
        }
    ]


def test_forward_strategy_endpoint_rejects_invalid_forward_rate() -> None:
    payload = valid_payload()
    payload["forward_legs"] = [
        {"notional_usd": 300_000, "forward_rate": 0}
    ]

    response = client.post(URL, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [
        {
            "field": "forward_rate",
            "message": "远期汇率必须是大于 0 的有效数字",
        }
    ]
```

- [ ] **步骤 2：运行接口测试，确认路由返回 404**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_forward_strategy_api.py -v
```

预期：成功案例得到 404，证明新接口尚未注册。

- [ ] **步骤 3：增加友好字段错误**

在 `python/backend/errors.py` 的 `FIELD_MESSAGES` 增加：

```python
    "forward_legs": "请至少输入一笔远期交易",
    "forward_rate": "远期汇率必须是大于 0 的有效数字",
```

`assumed_maturity_spot` 和 `notional_usd` 继续使用现有中文信息。

- [ ] **步骤 4：建立并注册独立路由**

新建 `python/backend/routes/forward_strategy.py`：

```python
from fastapi import APIRouter

from backend.forward_strategy.schemas import (
    ForwardStrategyScenarioRequest,
    ForwardStrategyScenarioResponse,
)
from backend.forward_strategy.service import (
    calculate_forward_strategy_scenario,
)


router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.post(
    "/forward-strategy/scenario",
    response_model=ForwardStrategyScenarioResponse,
)
def forward_strategy_scenario(
    payload: ForwardStrategyScenarioRequest,
) -> ForwardStrategyScenarioResponse:
    return calculate_forward_strategy_scenario(payload)
```

在 `python/backend/main.py` 导入：

```python
from backend.routes.forward_strategy import router as forward_strategy_router
```

在 `create_app()` 中注册：

```python
    app.include_router(forward_strategy_router)
```

- [ ] **步骤 5：运行远期接口和原分析接口测试**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_forward_strategy_api.py tests/backend/test_no_hedge_api.py tests/backend/test_no_hedge_probability_api.py tests/backend/test_automatic_no_hedge_probability_api.py -v
```

预期：新接口成功与中文错误测试通过，原接口不受影响。

- [ ] **步骤 6：运行全部后端测试**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest -q
```

预期：全部现有和新增测试通过；仅可保留项目原有 `StarletteDeprecationWarning`。

- [ ] **步骤 7：检查范围并保存接口**

运行：

```bash
git diff --check
git status --short
```

预期：没有空白符错误；未保存改动只包含远期路由、主应用注册、中文字段错误和 API 测试。

保存：

```bash
git add python/backend/routes/forward_strategy.py python/backend/main.py python/backend/errors.py python/tests/backend/test_forward_strategy_api.py
git commit -m "feat: expose forward strategy scenarios"
```

---

## 最终验证清单

- [ ] 在独立工作区运行全部 Python 测试并确认零失败。
- [ ] 确认原不套保、手动概率和自动概率接口测试继续通过。
- [ ] 确认一笔和多笔远期都能人工复算。
- [ ] 确认美元应收、持有美元和美元应付自动匹配正确方向。
- [ ] 确认相同带符号差额对收入和成本产生正确的改善/恶化判断。
- [ ] 确认部分、完全和超额套保金额及状态正确。
- [ ] 确认超额套保仍计算并返回固定风险提示。
- [ ] 确认没有目标时目标比较为空，有目标时两套比较都正确。
- [ ] 确认所有人民币正式结果统一保留两位且中间值不提前舍入。
- [ ] 确认新接口没有访问 ING、FRED 或其他网络。
- [ ] 确认 `python/requirements.txt` 未修改。
- [ ] 在 `/docs` 或 `TestClient` 使用设计文档中的 660 万、669 万案例人工测试。
- [ ] 确认 `git diff --check` 无错误且功能分支无未保存改动。
