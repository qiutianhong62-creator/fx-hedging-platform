# Automatic Forward Strategy Probability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个自动概率接口，在同一套 USD/CNY 市场预测分布下比较用户的一套多笔远期策略与完全不套保。

**Architecture:** 保留第七阶段确定性远期计算器作为唯一现金流公式来源；新增纯概率计算模块负责分位数、目标概率、策略胜率和范围变化，再由自动分析协调服务注入现有 ING 到期预测与 FRED 历史波动率。路由只负责依赖注入和 HTTP 响应，不在 API 层编写金融公式。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、标准库 `statistics.NormalDist`、pytest、FastAPI TestClient。

## Global Constraints

- 货币对仅支持 `USD/CNY`，报价口径为 `CNY per 1 USD`。
- 只比较完全不套保与用户当前输入的一套远期策略。
- 用户不输入预测汇率或波动率；接口使用现有 ING 预测与 FRED 历史数据服务。
- 所有远期使用敞口的统一到期日，方向由敞口类型自动决定。
- 允许部分、全额和超额套保；超额套保必须保留现有风险提示。
- 不增加随机模拟、蒙特卡洛或新的第三方依赖。
- 目标金额可选；省略时目标概率返回 `null`。
- 外部数据不可用时返回现有错误，不使用虚构默认值。
- 金额最终保留两位小数，概率限制在 `[0, 1]`。
- 本阶段不返回完整概率曲线、密集概率点、多策略结果或交易建议。
- 设计依据：`docs/superpowers/specs/2026-07-31-phase-8-automatic-forward-strategy-probability-design.md`。

---

## File Map

- Modify: `python/backend/forward_strategy/schemas.py` — 定义自动概率请求、金额区间、目标概率、策略比较和响应模型。
- Create: `python/backend/forward_strategy/probability.py` — 纯概率计算；不访问网络、缓存或系统时间。
- Modify: `python/backend/automatic_analysis/schemas.py` — 在纯概率响应上附加现有数据来源。
- Modify: `python/backend/automatic_analysis/service.py` — 协调预测服务、市场历史服务与纯计算器。
- Modify: `python/backend/routes/forward_strategy.py` — 暴露自动概率接口并提供可替换依赖。
- Create: `python/tests/backend/test_forward_strategy_probability_models.py` — 请求与响应模型校验。
- Create: `python/tests/backend/test_forward_strategy_probability.py` — 纯概率金额、目标、胜率和范围变化测试。
- Create: `python/tests/backend/test_automatic_forward_strategy_probability_service.py` — 外部数据协调与错误传播测试。
- Create: `python/tests/backend/test_automatic_forward_strategy_probability_api.py` — HTTP 契约测试。
- Modify: `README.md` — 记录新接口和人工测试样例。

---

### Task 1: Define the probability request and response contract

**Files:**
- Modify: `python/backend/forward_strategy/schemas.py`
- Create: `python/tests/backend/test_forward_strategy_probability_models.py`

**Interfaces:**
- Consumes: `AnalysisInput`, `DistributionMetadata`, `ResultKind`, `ForwardLegInput`, `ForwardCoverage`。
- Produces: `ForwardStrategyProbabilityRequest`, `ForwardProbabilityDistribution`, `StrategyProbabilityResult`, `ForwardStrategyProbabilityComparison`, `ForwardStrategyProbabilityResponse`。

- [ ] **Step 1: Write the failing model tests**

Create `python/tests/backend/test_forward_strategy_probability_models.py`:

```python
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.forward_strategy.schemas import (
    ForwardStrategyProbabilityRequest,
    RangeChange,
)


def valid_payload(**updates) -> dict[str, object]:
    payload: dict[str, object] = {
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": date.today() + timedelta(days=180),
        "target_cny": 6_680_000,
        "forward_legs": [
            {"notional_usd": 300_000, "forward_rate": 6.80},
            {"notional_usd": 200_000, "forward_rate": 6.75},
        ],
    }
    payload.update(updates)
    return payload


def test_probability_request_needs_no_market_assumptions() -> None:
    request = ForwardStrategyProbabilityRequest(**valid_payload())

    assert request.notional_usd == 1_000_000
    assert len(request.forward_legs) == 2
    assert "assumed_maturity_spot" not in request.model_fields
    assert "assumed_expected_maturity_spot" not in request.model_fields
    assert "assumed_annualized_volatility_pct" not in request.model_fields


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("notional_usd", float("inf")),
        ("target_cny", float("nan")),
    ],
)
def test_probability_request_rejects_non_finite_amounts(
    field: str,
    value: float,
) -> None:
    with pytest.raises(ValidationError):
        ForwardStrategyProbabilityRequest(
            **valid_payload(**{field: value})
        )


def test_probability_request_requires_a_forward_leg() -> None:
    with pytest.raises(ValidationError):
        ForwardStrategyProbabilityRequest(**valid_payload(forward_legs=[]))


def test_range_change_has_explicit_values() -> None:
    assert RangeChange.REDUCED == "reduced"
    assert RangeChange.UNCHANGED == "unchanged"
    assert RangeChange.INCREASED == "increased"
```

- [ ] **Step 2: Run the model tests and verify they fail**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_forward_strategy_probability_models.py -v
```

Expected: collection fails because `ForwardStrategyProbabilityRequest` and `RangeChange` do not exist.

- [ ] **Step 3: Add the complete request and response models**

Append the following structures to `python/backend/forward_strategy/schemas.py`, and add `DistributionMetadata` to its existing import from `backend.models`:

```python
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


class ForwardStrategyProbabilityResponse(BaseModel):
    status: Literal["calculated"] = "calculated"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    result_kind: ResultKind
    distribution: ForwardProbabilityDistribution
    no_hedge: StrategyProbabilityResult
    forward_strategy: ForwardStrategyProbabilityResult
    comparison: ForwardStrategyProbabilityComparison
```

- [ ] **Step 4: Run the model tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_forward_strategy_probability_models.py python/tests/backend/test_forward_strategy_models.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the contract**

```bash
git add python/backend/forward_strategy/schemas.py python/tests/backend/test_forward_strategy_probability_models.py
git commit -m "feat: define forward strategy probability contract"
```

---

### Task 2: Calculate expected amounts and probability ranges

**Files:**
- Create: `python/backend/forward_strategy/probability.py`
- Create: `python/tests/backend/test_forward_strategy_probability.py`

**Interfaces:**
- Consumes: `ForwardStrategyProbabilityRequest`, `calculate_forward_strategy_scenario()`, `build_lognormal_distribution()`。
- Produces: `scenario_amounts_at_spot(payload, spot) -> ScenarioAmounts` and `calculate_amount_range(payload, distribution, *, probability, lower_percentile, upper_percentile, strategy) -> AmountProbabilityRange`。

- [ ] **Step 1: Write failing tests for expected values and ordered ranges**

Create `python/tests/backend/test_forward_strategy_probability.py` with shared request construction and these initial tests:

```python
from datetime import date, timedelta

import pytest

from backend.forward_strategy.probability import (
    calculate_amount_range,
    scenario_amounts_at_spot,
)
from backend.forward_strategy.schemas import (
    ForwardStrategyProbabilityRequest,
)
from backend.services.distributions import build_lognormal_distribution


VALUATION_DATE = date.today()
MATURITY_DATE = VALUATION_DATE + timedelta(days=180)


def request(
    *,
    exposure_type: str = "usd_receivable",
    exposure_usd: float = 1_000_000,
    target_cny: float | None = None,
    legs: list[dict[str, float]] | None = None,
) -> ForwardStrategyProbabilityRequest:
    return ForwardStrategyProbabilityRequest(
        exposure_type=exposure_type,
        notional_usd=exposure_usd,
        maturity_date=MATURITY_DATE,
        target_cny=target_cny,
        forward_legs=legs or [
            {"notional_usd": 300_000, "forward_rate": 6.80},
            {"notional_usd": 200_000, "forward_rate": 6.75},
        ],
    )


def distribution():
    return build_lognormal_distribution(
        expected_spot=6.72,
        annualized_volatility_pct=4.2,
        maturity_date=MATURITY_DATE,
        valuation_date=VALUATION_DATE,
    )


def test_expected_amounts_reuse_scenario_cashflows() -> None:
    result = scenario_amounts_at_spot(request(), 6.72)

    assert result.no_hedge_amount_cny == 6_720_000
    assert result.strategy_amount_cny == 6_750_000
    assert result.coverage.coverage_ratio == 0.5


def test_partial_hedge_has_a_narrower_ordered_range() -> None:
    no_hedge = calculate_amount_range(
        request(), distribution(), probability=0.90,
        lower_percentile=0.05, upper_percentile=0.95, strategy=False,
    )
    strategy = calculate_amount_range(
        request(), distribution(), probability=0.90,
        lower_percentile=0.05, upper_percentile=0.95, strategy=True,
    )
    assert no_hedge.minimum_amount_cny < no_hedge.maximum_amount_cny
    assert strategy.minimum_amount_cny < strategy.maximum_amount_cny
    assert (
        strategy.maximum_amount_cny - strategy.minimum_amount_cny
        < no_hedge.maximum_amount_cny - no_hedge.minimum_amount_cny
    )


def test_full_hedge_has_one_fixed_amount() -> None:
    payload = request(
        legs=[{"notional_usd": 1_000_000, "forward_rate": 6.80}]
    )
    result = scenario_amounts_at_spot(payload, 6.72)
    amount_range = calculate_amount_range(
        payload, distribution(), probability=0.90,
        lower_percentile=0.05, upper_percentile=0.95, strategy=True,
    )

    assert result.strategy_amount_cny == 6_800_000
    assert amount_range.minimum_amount_cny == 6_800_000
    assert amount_range.maximum_amount_cny == 6_800_000


def test_over_hedge_range_is_sorted_when_amount_slope_is_negative() -> None:
    payload = request(
        legs=[{"notional_usd": 1_500_000, "forward_rate": 6.80}]
    )
    amount_range = calculate_amount_range(
        payload, distribution(), probability=0.90,
        lower_percentile=0.05, upper_percentile=0.95, strategy=True,
    )

    assert amount_range.minimum_amount_cny < amount_range.maximum_amount_cny
    scenario = scenario_amounts_at_spot(payload, 6.72)
    assert scenario.coverage.status == "over_hedged"
    assert scenario.coverage.warnings[0].code == "over_hedged"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_forward_strategy_probability.py -v
```

Expected: collection fails because `backend.forward_strategy.probability` does not exist.

- [ ] **Step 3: Implement the pure amount and range calculation**

Create `python/backend/forward_strategy/probability.py`. Use the existing deterministic calculator for every displayed amount so there is only one cashflow formula:

```python
from dataclasses import dataclass

from backend.forward_strategy.schemas import (
    AmountProbabilityRange,
    ForwardCoverage,
    ForwardStrategyProbabilityRequest,
)
from backend.forward_strategy.service import (
    calculate_forward_strategy_scenario,
)
from backend.forward_strategy.schemas import ForwardStrategyScenarioRequest
from backend.models import ResultKind
from backend.services.distributions import (
    LognormalDistribution,
)


@dataclass(frozen=True)
class ScenarioAmounts:
    result_kind: ResultKind
    no_hedge_amount_cny: float
    strategy_amount_cny: float
    coverage: ForwardCoverage


def scenario_amounts_at_spot(
    payload: ForwardStrategyProbabilityRequest,
    spot: float,
) -> ScenarioAmounts:
    scenario_request = ForwardStrategyScenarioRequest(
        **payload.model_dump(),
        assumed_maturity_spot=spot,
    )
    result = calculate_forward_strategy_scenario(scenario_request)
    return ScenarioAmounts(
        result_kind=result.result_kind,
        no_hedge_amount_cny=result.no_hedge_amount_cny,
        strategy_amount_cny=result.strategy_amount_cny,
        coverage=result.coverage,
    )


def calculate_amount_range(
    payload: ForwardStrategyProbabilityRequest,
    distribution: LognormalDistribution,
    *,
    probability: float,
    lower_percentile: float,
    upper_percentile: float,
    strategy: bool,
) -> AmountProbabilityRange:
    lower_spot = distribution.quantile(lower_percentile)
    upper_spot = distribution.quantile(upper_percentile)
    lower_result = scenario_amounts_at_spot(payload, lower_spot)
    upper_result = scenario_amounts_at_spot(payload, upper_spot)
    values = (
        [lower_result.strategy_amount_cny, upper_result.strategy_amount_cny]
        if strategy
        else [lower_result.no_hedge_amount_cny, upper_result.no_hedge_amount_cny]
    )
    return AmountProbabilityRange(
        probability=probability,
        minimum_amount_cny=min(values),
        maximum_amount_cny=max(values),
    )
```

- [ ] **Step 4: Run amount/range tests and existing scenario tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_forward_strategy_probability.py python/tests/backend/test_forward_strategy_service.py -v
```

Expected: all current tests pass, including the negative-slope over-hedge case.

- [ ] **Step 5: Commit amount and range calculation**

```bash
git add python/backend/forward_strategy/probability.py python/tests/backend/test_forward_strategy_probability.py
git commit -m "feat: calculate forward strategy probability ranges"
```

---

### Task 3: Add target probabilities, strategy win probability, and range change

**Files:**
- Modify: `python/backend/forward_strategy/probability.py`
- Modify: `python/tests/backend/test_forward_strategy_probability.py`

**Interfaces:**
- Consumes: Task 2 distribution and amount range helpers。
- Produces: `calculate_forward_strategy_probability(payload, *, expected_maturity_spot, annualized_volatility_pct, valuation_date, source_type, is_market_forecast) -> ForwardStrategyProbabilityResponse`, including targets, break-even probability and `RangeChange`。

- [ ] **Step 1: Add failing tests for all comparison branches**

First extend the existing probability import in `python/tests/backend/test_forward_strategy_probability.py`:

```python
from backend.forward_strategy.probability import (
    calculate_amount_range,
    calculate_forward_strategy_probability,
    scenario_amounts_at_spot,
)
```

Then append:

```python
def calculate(payload: ForwardStrategyProbabilityRequest):
    return calculate_forward_strategy_probability(
        payload,
        expected_maturity_spot=6.72,
        annualized_volatility_pct=4.2,
        valuation_date=VALUATION_DATE,
        source_type="market_data",
        is_market_forecast=True,
    )


def test_receivable_target_and_strategy_win_probabilities() -> None:
    result = calculate(request(target_cny=6_680_000))

    assert result.no_hedge.target_probability is not None
    assert result.forward_strategy.target_probability is not None
    assert result.no_hedge.target_probability.critical_spot == pytest.approx(6.68)
    assert 0 <= result.no_hedge.target_probability.probability_met <= 1
    assert 0 <= result.forward_strategy.target_probability.probability_met <= 1
    assert result.comparison.break_even_spot == pytest.approx(6.78)
    assert (
        result.comparison.probability_strategy_better
        + result.comparison.probability_no_hedge_better
        == pytest.approx(1.0)
    )


def test_payable_reverses_target_and_better_inequalities() -> None:
    receivable = calculate(request(target_cny=6_680_000))
    payable = calculate(
        request(exposure_type="usd_payable", target_cny=6_680_000)
    )

    assert payable.no_hedge.target_probability is not None
    assert payable.no_hedge.target_probability.probability_met == pytest.approx(
        1 - receivable.no_hedge.target_probability.probability_met
    )
    assert payable.comparison.probability_strategy_better == pytest.approx(
        1 - receivable.comparison.probability_strategy_better
    )


def test_full_hedge_target_probability_is_zero_or_one() -> None:
    passing = calculate(
        request(
            target_cny=6_750_000,
            legs=[{"notional_usd": 1_000_000, "forward_rate": 6.80}],
        )
    )
    missing = calculate(
        request(
            target_cny=6_850_000,
            legs=[{"notional_usd": 1_000_000, "forward_rate": 6.80}],
        )
    )

    assert passing.forward_strategy.target_probability is not None
    assert passing.forward_strategy.target_probability.critical_spot is None
    assert passing.forward_strategy.target_probability.probability_met == 1
    assert missing.forward_strategy.target_probability is not None
    assert missing.forward_strategy.target_probability.probability_met == 0


def test_target_is_null_when_user_omits_it() -> None:
    result = calculate(request(target_cny=None))

    assert result.no_hedge.target_probability is None
    assert result.forward_strategy.target_probability is None


@pytest.mark.parametrize(
    ("hedge_notional", "expected_change"),
    [
        (500_000, "reduced"),
        (2_000_000, "unchanged"),
        (2_500_000, "increased"),
    ],
)
def test_range_change_can_reduce_stay_equal_or_increase(
    hedge_notional: float,
    expected_change: str,
) -> None:
    result = calculate(
        request(
            legs=[{"notional_usd": hedge_notional, "forward_rate": 6.80}]
        )
    )

    assert result.comparison.wide_range_90_width.change == expected_change
```

- [ ] **Step 2: Run the new tests and verify the missing behavior**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_forward_strategy_probability.py -v
```

Expected: the new target, comparison or range-change assertions fail before their implementation is complete.

- [ ] **Step 3: Implement a general linear target probability helper**

Extend the imports in `python/backend/forward_strategy/probability.py` with the exact names used by the final calculator:

```python
from datetime import date
from decimal import Decimal
from typing import Literal

from backend.forward_strategy.schemas import (
    ForwardProbabilityDistribution,
    ForwardStrategyProbabilityResult,
    ForwardStrategyProbabilityComparison,
    ForwardStrategyProbabilityResponse,
    ForwardTargetProbability,
    RangeChange,
    RangeWidthComparison,
    SpotProbabilityRange,
    StrategyProbabilityResult,
)
from backend.models import ExposureType
from backend.services.distributions import build_lognormal_distribution
from backend.services.scenario_common import cny_amount
```

Then add:

```python
def _target_probability(
    *,
    target_cny: float | None,
    intercept: float,
    slope: float,
    exposure_type: ExposureType,
    distribution: LognormalDistribution,
) -> ForwardTargetProbability | None:
    if target_cny is None:
        return None
    if slope == 0:
        met = (
            intercept <= target_cny
            if exposure_type is ExposureType.USD_PAYABLE
            else intercept >= target_cny
        )
        probability_met = 1.0 if met else 0.0
        critical_spot = None
    else:
        critical_spot = (target_cny - intercept) / slope
        probability_below = distribution.cdf(critical_spot)
        amount_condition_is_below = (
            exposure_type is ExposureType.USD_PAYABLE
        )
        spot_condition_is_below = (
            amount_condition_is_below if slope > 0 else not amount_condition_is_below
        )
        probability_met = (
            probability_below
            if spot_condition_is_below
            else 1.0 - probability_below
        )
    probability_met = min(1.0, max(0.0, probability_met))
    return ForwardTargetProbability(
        target_cny=target_cny,
        critical_spot=critical_spot,
        probability_met=probability_met,
        probability_missed=1.0 - probability_met,
    )
```

Use `intercept=0, slope=E` for no hedge and `intercept=C, slope=E-H` for the forward strategy. Calculate `E`, `H`, and `C` with `Decimal(str(value))` to avoid premature binary rounding.

- [ ] **Step 4: Implement break-even, win probability and width comparison**

Add helpers that follow the approved economic direction:

```python
def _strategy_better_probability(
    *,
    break_even_spot: float,
    exposure_type: ExposureType,
    distribution: LognormalDistribution,
) -> float:
    probability_below = distribution.cdf(break_even_spot)
    if exposure_type is ExposureType.USD_PAYABLE:
        return 1.0 - probability_below
    return probability_below


def _range_width_comparison(
    no_hedge: AmountProbabilityRange,
    strategy: AmountProbabilityRange,
) -> RangeWidthComparison:
    no_hedge_width = cny_amount(
        Decimal(str(no_hedge.maximum_amount_cny))
        - Decimal(str(no_hedge.minimum_amount_cny))
    )
    strategy_width = cny_amount(
        Decimal(str(strategy.maximum_amount_cny))
        - Decimal(str(strategy.minimum_amount_cny))
    )
    difference = strategy_width - no_hedge_width
    change = (
        RangeChange.REDUCED
        if difference < 0
        else RangeChange.INCREASED
        if difference > 0
        else RangeChange.UNCHANGED
    )
    return RangeWidthComparison(
        no_hedge_width_cny=float(no_hedge_width),
        strategy_width_cny=float(strategy_width),
        strategy_minus_no_hedge_cny=float(difference),
        change=change,
    )
```

Build the complete response with:

```python
def _spot_range(
    distribution: LognormalDistribution,
    *,
    probability: float,
    lower_percentile: float,
    upper_percentile: float,
) -> SpotProbabilityRange:
    return SpotProbabilityRange(
        probability=probability,
        lower_spot=distribution.quantile(lower_percentile),
        upper_spot=distribution.quantile(upper_percentile),
    )


def calculate_forward_strategy_probability(
    payload: ForwardStrategyProbabilityRequest,
    *,
    expected_maturity_spot: float,
    annualized_volatility_pct: float,
    valuation_date: date | None = None,
    source_type: Literal["assumption", "market_data"] = "assumption",
    is_market_forecast: bool = False,
) -> ForwardStrategyProbabilityResponse:
    distribution = build_lognormal_distribution(
        expected_spot=expected_maturity_spot,
        annualized_volatility_pct=annualized_volatility_pct,
        maturity_date=payload.maturity_date,
        valuation_date=valuation_date,
    )
    expected = scenario_amounts_at_spot(payload, expected_maturity_spot)
    typical_spot = _spot_range(
        distribution,
        probability=0.50,
        lower_percentile=0.25,
        upper_percentile=0.75,
    )
    wide_spot = _spot_range(
        distribution,
        probability=0.90,
        lower_percentile=0.05,
        upper_percentile=0.95,
    )
    no_hedge_typical = calculate_amount_range(
        payload,
        distribution,
        probability=0.50,
        lower_percentile=0.25,
        upper_percentile=0.75,
        strategy=False,
    )
    no_hedge_wide = calculate_amount_range(
        payload,
        distribution,
        probability=0.90,
        lower_percentile=0.05,
        upper_percentile=0.95,
        strategy=False,
    )
    strategy_typical = calculate_amount_range(
        payload,
        distribution,
        probability=0.50,
        lower_percentile=0.25,
        upper_percentile=0.75,
        strategy=True,
    )
    strategy_wide = calculate_amount_range(
        payload,
        distribution,
        probability=0.90,
        lower_percentile=0.05,
        upper_percentile=0.95,
        strategy=True,
    )

    exposure = Decimal(str(payload.notional_usd))
    total_forward = sum(
        (Decimal(str(leg.notional_usd)) for leg in payload.forward_legs),
        Decimal("0"),
    )
    locked_cny = sum(
        (
            Decimal(str(leg.notional_usd))
            * Decimal(str(leg.forward_rate))
            for leg in payload.forward_legs
        ),
        Decimal("0"),
    )
    break_even_spot = float(locked_cny / total_forward)
    probability_strategy_better = _strategy_better_probability(
        break_even_spot=break_even_spot,
        exposure_type=payload.exposure_type,
        distribution=distribution,
    )

    return ForwardStrategyProbabilityResponse(
        result_kind=expected.result_kind,
        distribution=ForwardProbabilityDistribution(
            source_type=source_type,
            is_market_forecast=is_market_forecast,
            assumed_expected_maturity_spot=expected_maturity_spot,
            assumed_annualized_volatility_pct=annualized_volatility_pct,
            horizon_days=distribution.horizon_days,
            typical_spot_range_50=typical_spot,
            wide_spot_range_90=wide_spot,
        ),
        no_hedge=StrategyProbabilityResult(
            expected_amount_cny=expected.no_hedge_amount_cny,
            typical_range_50=no_hedge_typical,
            wide_range_90=no_hedge_wide,
            target_probability=_target_probability(
                target_cny=payload.target_cny,
                intercept=0.0,
                slope=float(exposure),
                exposure_type=payload.exposure_type,
                distribution=distribution,
            ),
        ),
        forward_strategy=ForwardStrategyProbabilityResult(
            expected_amount_cny=expected.strategy_amount_cny,
            typical_range_50=strategy_typical,
            wide_range_90=strategy_wide,
            target_probability=_target_probability(
                target_cny=payload.target_cny,
                intercept=float(locked_cny),
                slope=float(exposure - total_forward),
                exposure_type=payload.exposure_type,
                distribution=distribution,
            ),
            coverage=expected.coverage,
        ),
        comparison=ForwardStrategyProbabilityComparison(
            break_even_spot=break_even_spot,
            probability_strategy_better=probability_strategy_better,
            probability_no_hedge_better=1.0 - probability_strategy_better,
            wide_range_90_width=_range_width_comparison(
                no_hedge_wide,
                strategy_wide,
            ),
        ),
    )
```

Use the expected deterministic scenario's `result_kind` and `coverage`, which preserves the existing direction and over-hedge warning behavior.

- [ ] **Step 5: Run pure probability and regression tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_forward_strategy_probability.py python/tests/backend/test_forward_strategy_service.py python/tests/backend/test_no_hedge_probability_service.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit the comparisons**

```bash
git add python/backend/forward_strategy/probability.py python/tests/backend/test_forward_strategy_probability.py
git commit -m "feat: compare forward strategy probabilities"
```

---

### Task 4: Orchestrate ING forecast and FRED volatility

**Files:**
- Modify: `python/backend/automatic_analysis/schemas.py`
- Modify: `python/backend/automatic_analysis/service.py`
- Create: `python/tests/backend/test_automatic_forward_strategy_probability_service.py`

**Interfaces:**
- Consumes: existing `ForecastLookup.get_estimate()`, `MarketHistoryLookup.get_summary()`, and Task 3 `calculate_forward_strategy_probability()`。
- Produces: `AutomaticForwardStrategyProbabilityService.calculate(payload) -> AutomaticForwardStrategyProbabilityResponse`。

- [ ] **Step 1: Write failing orchestration tests**

Create `python/tests/backend/test_automatic_forward_strategy_probability_service.py`. Reuse the fixed fakes from `test_automatic_no_hedge_probability_service.py`:

```python
from datetime import date, timedelta

import pytest

from backend.automatic_analysis.service import (
    AutomaticForwardStrategyProbabilityService,
)
from backend.forecast.errors import ForecastSourceUnavailableError
from backend.forward_strategy.schemas import ForwardStrategyProbabilityRequest
from backend.market.errors import MarketDataUnavailableError
from tests.backend.test_automatic_no_hedge_probability_service import (
    FakeForecastService,
    FakeMarketService,
    forecast_result,
    market_result,
)


MATURITY_DATE = date.today() + timedelta(days=180)


def payload() -> ForwardStrategyProbabilityRequest:
    return ForwardStrategyProbabilityRequest(
        exposure_type="usd_receivable",
        notional_usd=1_000_000,
        maturity_date=MATURITY_DATE,
        target_cny=6_800_000,
        forward_legs=[
            {"notional_usd": 500_000, "forward_rate": 6.80},
        ],
    )


def test_service_uses_forecast_and_historical_volatility() -> None:
    forecast = FakeForecastService()
    market = FakeMarketService()
    service = AutomaticForwardStrategyProbabilityService(
        forecast_service=forecast,
        market_history_service=market,
    )

    result = service.calculate(payload())

    assert forecast.calls == [MATURITY_DATE]
    assert market.calls == 1
    assert result.distribution.assumed_expected_maturity_spot == 6.72
    assert result.distribution.assumed_annualized_volatility_pct == 4.2
    assert result.data_sources.forecast == forecast_result()
    assert result.data_sources.market_history == market_result()


def test_forecast_error_stops_before_market_lookup() -> None:
    market = FakeMarketService()
    service = AutomaticForwardStrategyProbabilityService(
        forecast_service=FakeForecastService(
            error=ForecastSourceUnavailableError()
        ),
        market_history_service=market,
    )

    with pytest.raises(ForecastSourceUnavailableError):
        service.calculate(payload())
    assert market.calls == 0


def test_market_error_is_not_replaced_by_defaults() -> None:
    service = AutomaticForwardStrategyProbabilityService(
        forecast_service=FakeForecastService(),
        market_history_service=FakeMarketService(
            error=MarketDataUnavailableError()
        ),
    )

    with pytest.raises(MarketDataUnavailableError):
        service.calculate(payload())
```

- [ ] **Step 2: Run the service tests and verify they fail**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_automatic_forward_strategy_probability_service.py -v
```

Expected: import fails because `AutomaticForwardStrategyProbabilityService` does not exist.

- [ ] **Step 3: Add the automatic response schema**

Modify `python/backend/automatic_analysis/schemas.py`:

```python
from backend.forward_strategy.schemas import ForwardStrategyProbabilityResponse


class AutomaticForwardStrategyProbabilityResponse(
    ForwardStrategyProbabilityResponse
):
    data_sources: AutomaticAnalysisDataSources
```

- [ ] **Step 4: Add the orchestration service**

Modify `python/backend/automatic_analysis/service.py`:

```python
from backend.automatic_analysis.schemas import (
    AutomaticForwardStrategyProbabilityResponse,
)
from backend.forward_strategy.probability import (
    calculate_forward_strategy_probability,
)
from backend.forward_strategy.schemas import ForwardStrategyProbabilityRequest


class AutomaticForwardStrategyProbabilityService:
    def __init__(
        self,
        *,
        forecast_service: ForecastLookup,
        market_history_service: MarketHistoryLookup,
    ) -> None:
        self._forecast_service = forecast_service
        self._market_history_service = market_history_service

    def calculate(
        self,
        payload: ForwardStrategyProbabilityRequest,
    ) -> AutomaticForwardStrategyProbabilityResponse:
        forecast = self._forecast_service.get_estimate(payload.maturity_date)
        market_history = self._market_history_service.get_summary()
        analysis = calculate_forward_strategy_probability(
            payload,
            expected_maturity_spot=forecast.expected_maturity_spot,
            annualized_volatility_pct=(
                market_history.historical_volatility.annualized_volatility_pct
            ),
            valuation_date=forecast.valuation_date,
            source_type="market_data",
            is_market_forecast=True,
        )
        return AutomaticForwardStrategyProbabilityResponse(
            **analysis.model_dump(),
            data_sources=AutomaticAnalysisDataSources(
                forecast=forecast,
                market_history=market_history,
            ),
        )
```

- [ ] **Step 5: Run both automatic-service suites**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_automatic_forward_strategy_probability_service.py python/tests/backend/test_automatic_no_hedge_probability_service.py -v
```

Expected: all tests pass and existing no-hedge orchestration remains unchanged.

- [ ] **Step 6: Commit the orchestration layer**

```bash
git add python/backend/automatic_analysis/schemas.py python/backend/automatic_analysis/service.py python/tests/backend/test_automatic_forward_strategy_probability_service.py
git commit -m "feat: automate forward strategy probability inputs"
```

---

### Task 5: Expose the API and document manual verification

**Files:**
- Modify: `python/backend/routes/forward_strategy.py`
- Create: `python/tests/backend/test_automatic_forward_strategy_probability_api.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `AutomaticForwardStrategyProbabilityService` and existing forecast/market dependency providers。
- Produces: `POST /api/v1/analysis/forward-strategy/automatic-probability`。

- [ ] **Step 1: Write failing API contract tests**

Create `python/tests/backend/test_automatic_forward_strategy_probability_api.py`:

```python
from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend.automatic_analysis.service import (
    AutomaticForwardStrategyProbabilityService,
)
from backend.forecast.errors import ForecastSourceUnavailableError
from backend.main import app
from backend.routes.forward_strategy import (
    get_automatic_forward_strategy_probability_service,
)
from tests.backend.test_automatic_no_hedge_probability_service import (
    FakeForecastService,
    FakeMarketService,
)


client = TestClient(app)


def valid_payload() -> dict[str, object]:
    return {
        "currency_pair": "USD/CNY",
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": (date.today() + timedelta(days=180)).isoformat(),
        "target_cny": 6_800_000,
        "forward_legs": [
            {"notional_usd": 500_000, "forward_rate": 6.80},
        ],
    }


def automatic_service() -> AutomaticForwardStrategyProbabilityService:
    return AutomaticForwardStrategyProbabilityService(
        forecast_service=FakeForecastService(),
        market_history_service=FakeMarketService(),
    )


def test_endpoint_returns_strategy_comparison_without_assumptions() -> None:
    app.dependency_overrides[
        get_automatic_forward_strategy_probability_service
    ] = automatic_service
    try:
        response = client.post(
            "/api/v1/analysis/forward-strategy/automatic-probability",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["distribution"]["source_type"] == "market_data"
    assert body["no_hedge"]["expected_amount_cny"] == 6_720_000
    assert body["forward_strategy"]["expected_amount_cny"] == 6_760_000
    assert 0 <= body["comparison"]["probability_strategy_better"] <= 1
    assert body["forward_strategy"]["coverage"]["coverage_ratio"] == 0.5
    assert body["data_sources"]["forecast"]["sources"][0]["institution"] == "ING"
    assert body["data_sources"]["market_history"]["source"]["provider"] == "FRED"


def test_endpoint_preserves_forecast_error_contract() -> None:
    app.dependency_overrides[
        get_automatic_forward_strategy_probability_service
    ] = lambda: AutomaticForwardStrategyProbabilityService(
        forecast_service=FakeForecastService(
            error=ForecastSourceUnavailableError()
        ),
        market_history_service=FakeMarketService(),
    )
    try:
        response = client.post(
            "/api/v1/analysis/forward-strategy/automatic-probability",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "forecast_source_unavailable"


def test_endpoint_rejects_empty_forward_legs() -> None:
    payload = valid_payload()
    payload["forward_legs"] = []

    response = client.post(
        "/api/v1/analysis/forward-strategy/automatic-probability",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
```

- [ ] **Step 2: Run the API tests and verify they fail**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_automatic_forward_strategy_probability_api.py -v
```

Expected: import or route lookup fails because the dependency provider and endpoint do not exist.

- [ ] **Step 3: Add dependency injection and the endpoint**

Modify `python/backend/routes/forward_strategy.py`:

```python
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.automatic_analysis.schemas import (
    AutomaticForwardStrategyProbabilityResponse,
)
from backend.automatic_analysis.service import (
    AutomaticForwardStrategyProbabilityService,
)
from backend.forward_strategy.schemas import ForwardStrategyProbabilityRequest
from backend.routes.forecast import get_maturity_forecast_service
from backend.routes.market import get_market_history_service


@lru_cache
def get_automatic_forward_strategy_probability_service(
) -> AutomaticForwardStrategyProbabilityService:
    return AutomaticForwardStrategyProbabilityService(
        forecast_service=get_maturity_forecast_service(),
        market_history_service=get_market_history_service(),
    )


@router.post(
    "/forward-strategy/automatic-probability",
    response_model=AutomaticForwardStrategyProbabilityResponse,
)
def automatic_forward_strategy_probability(
    payload: ForwardStrategyProbabilityRequest,
    service: Annotated[
        AutomaticForwardStrategyProbabilityService,
        Depends(get_automatic_forward_strategy_probability_service),
    ],
) -> AutomaticForwardStrategyProbabilityResponse:
    return service.calculate(payload)
```

Keep the existing `/forward-strategy/scenario` route unchanged.

- [ ] **Step 4: Run the endpoint tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_automatic_forward_strategy_probability_api.py python/tests/backend/test_forward_strategy_api.py -v
```

Expected: all tests pass and both old and new routes remain available.

- [ ] **Step 5: Add a README manual-test section**

Append a concise section to `README.md` containing:

````markdown
### 第八阶段：远期策略自动概率比较

启动后端并打开 `http://127.0.0.1:8000/docs`，展开：

```text
POST /api/v1/analysis/forward-strategy/automatic-probability
```

用户只输入敞口、到期日、可选目标金额和真实远期报价。系统自动读取当前接入的机构预测与历史波动率，并在同一概率分布下返回不套保和远期策略的预计金额、50%与90%金额范围、目标达标概率、策略更优概率和范围变化。

当前预测仍是单一机构试验，不代表多机构共识，也不构成交易建议。
````

- [ ] **Step 6: Run formatting checks and the complete backend suite**

Run:

```bash
git diff --check
PYTHONPATH=python .venv/bin/python -m pytest python/tests -v
```

Expected: `git diff --check` has no output; all backend tests pass with no new warnings or failures.

- [ ] **Step 7: Start the API and perform one manual request**

Run:

```bash
.venv/bin/python -m uvicorn backend.main:app --app-dir python --reload
```

Open `http://127.0.0.1:8000/docs`, call the new endpoint with a future maturity date and confirm:

```text
expected no hedge amount = notional × expected maturity spot
expected strategy amount = expected no hedge amount + Σ[Ni × (Fi - expected spot)]
both probabilities are between 0 and 1
data_sources identifies ING and FRED
```

- [ ] **Step 8: Commit the API and documentation**

```bash
git add python/backend/routes/forward_strategy.py python/tests/backend/test_automatic_forward_strategy_probability_api.py README.md
git commit -m "feat: expose automatic forward strategy probability"
```

---

## Final Verification

- [ ] Run all Python tests from a clean shell:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests -v
```

- [ ] Confirm the worktree contains only intentional files:

```bash
git status --short
git log --oneline -6
```

- [ ] Compare implementation with every section of `docs/superpowers/specs/2026-07-31-phase-8-automatic-forward-strategy-probability-design.md`.

- [ ] Use `superpowers:verification-before-completion` before reporting success, then use `superpowers:finishing-a-development-branch` to offer merge/push choices.
