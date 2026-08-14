# Phase 10 Probability Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 USD/CNY 不套保与远期策略概率响应中，新增由 20 个主要汇率区间和左右尾部组成的完整概率剖面，同时返回区间概率、累计概率和人民币金额范围。

**Architecture:** 新建一个与业务无关的纯概率剖面生成器，只把现有 `LognormalDistribution` 切分为 P1–P99 的 20 个等宽区间及两个尾部。不套保服务和远期策略服务分别在同一组汇率边界上调用已有现金流计算器，并通过现有 Pydantic 响应类自动进入手动与市场数据驱动的 API。

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, pytest 8, Python `statistics.NormalDist`, `dataclasses`

## Global Constraints

- 第一版只支持 `USD/CNY`，不新增其他币种。
- 继续使用现有解析对数正态分布，不使用蒙特卡洛或任何随机抽样。
- 主要范围固定为 P1–P99，并分为恰好 20 个等宽汇率区间。
- P1 以下与 P99 以上必须作为开放尾部返回，不伪造有限金额区间。
- 概率使用 0 到 1 的未展示舍入浮点数；前端未来负责转换为百分比。
- 金额必须复用已有现金流计算器和人民币分舍入规则，不在剖面层复制金额公式。
- 现有 HTTP 请求字段不变，现有响应字段不删除或改名。
- 自动接口继续使用机构综合预测与 FRED 历史波动率；外部数据失败时不使用虚构默认值。
- 本阶段不修改前端，不新增期权、机构数据源或多到期日逻辑。
- 完成时现有 262 项后端测试必须全部继续通过。

## File Structure

- Create `python/backend/services/probability_profile.py`: 只负责从已构建的概率分布生成汇率区间、累计概率和左右尾部。
- Create `python/tests/backend/test_probability_profile.py`: 验证 20 个等宽区间、概率合计、累计单调性和确定性。
- Modify `python/backend/models.py`: 定义不套保概率剖面的 API 响应结构。
- Modify `python/backend/services/no_hedge_probability.py`: 把通用汇率剖面换算为不套保金额范围和尾部边界金额。
- Modify `python/tests/backend/test_no_hedge_probability_service.py`: 验证不套保剖面金额、区间和尾部。
- Modify `python/tests/backend/test_no_hedge_probability_api.py`: 验证手动 API 序列化合同。
- Modify `python/tests/backend/test_automatic_no_hedge_probability_api.py`: 验证自动 API 继承概率剖面且保留数据源。
- Modify `python/backend/forward_strategy/schemas.py`: 定义远期策略概率剖面的 API 响应结构。
- Modify `python/backend/forward_strategy/probability.py`: 在通用汇率边界上同时计算不套保与远期策略金额范围。
- Modify `python/tests/backend/test_forward_strategy_probability.py`: 验证部分、足额和超额套保的剖面金额。
- Modify `python/tests/backend/test_automatic_forward_strategy_probability_api.py`: 验证自动远期 API 的剖面、数据源和限制说明。
- Modify `README.md`: 新增第十阶段的手工测试说明和模型警示。

---

### Task 1: Pure Spot Probability Profile Generator

**Files:**
- Create: `python/backend/services/probability_profile.py`
- Create: `python/tests/backend/test_probability_profile.py`

**Interfaces:**
- Consumes: `backend.services.distributions.LognormalDistribution`
- Produces: `SpotProbabilityBucket`, `SpotProbabilityTail`, `SpotProbabilityProfile`, and `build_spot_probability_profile(distribution: LognormalDistribution) -> SpotProbabilityProfile`

- [ ] **Step 1: Write failing tests for interval geometry and probabilities**

Create `python/tests/backend/test_probability_profile.py`:

```python
from datetime import date, timedelta

import pytest

from backend.services.distributions import build_lognormal_distribution
from backend.services.probability_profile import (
    build_spot_probability_profile,
)


VALUATION_DATE = date(2030, 1, 1)


def make_distribution(*, days: int = 365, volatility_pct: float = 5.0):
    return build_lognormal_distribution(
        expected_spot=6.80,
        annualized_volatility_pct=volatility_pct,
        maturity_date=VALUATION_DATE + timedelta(days=days),
        valuation_date=VALUATION_DATE,
    )


def test_profile_has_twenty_contiguous_equal_width_buckets() -> None:
    profile = build_spot_probability_profile(make_distribution())

    assert profile.bucket_count == 20
    assert len(profile.intervals) == 20
    assert profile.intervals[0].lower_spot == pytest.approx(
        profile.core_lower_spot
    )
    assert profile.intervals[-1].upper_spot == pytest.approx(
        profile.core_upper_spot
    )
    widths = []
    for current, following in zip(
        profile.intervals,
        profile.intervals[1:],
    ):
        assert current.upper_spot == pytest.approx(following.lower_spot)
        widths.append(current.upper_spot - current.lower_spot)
    widths.append(
        profile.intervals[-1].upper_spot
        - profile.intervals[-1].lower_spot
    )
    assert max(widths) == pytest.approx(min(widths))


def test_profile_probabilities_cover_the_full_distribution() -> None:
    distribution = make_distribution()
    profile = build_spot_probability_profile(distribution)

    interval_total = sum(
        interval.interval_probability for interval in profile.intervals
    )
    total = (
        profile.lower_tail.probability
        + interval_total
        + profile.upper_tail.probability
    )
    assert profile.core_probability == pytest.approx(0.98)
    assert profile.lower_tail.probability == pytest.approx(0.01)
    assert profile.upper_tail.probability == pytest.approx(0.01)
    assert total == pytest.approx(1.0)
    for interval in profile.intervals:
        assert interval.interval_probability == pytest.approx(
            distribution.cdf(interval.upper_spot)
            - distribution.cdf(interval.lower_spot)
        )
        assert (
            interval.probability_below_upper
            + interval.probability_above_upper
        ) == pytest.approx(1.0)


def test_profile_cumulative_probabilities_are_monotonic() -> None:
    profile = build_spot_probability_profile(make_distribution())

    below = [item.probability_below_upper for item in profile.intervals]
    above = [item.probability_above_upper for item in profile.intervals]
    assert below == sorted(below)
    assert above == sorted(above, reverse=True)


@pytest.mark.parametrize(
    ("days", "volatility_pct"),
    [(30, 2.0), (365, 5.0), (730, 12.0)],
)
def test_profile_is_finite_and_deterministic(
    days: int,
    volatility_pct: float,
) -> None:
    distribution = make_distribution(
        days=days,
        volatility_pct=volatility_pct,
    )

    first = build_spot_probability_profile(distribution)
    second = build_spot_probability_profile(distribution)

    assert first == second
    assert first.core_lower_spot > 0
    assert first.core_upper_spot > first.core_lower_spot
```

- [ ] **Step 2: Run the new tests and confirm the missing module failure**

Run from `python/`:

```bash
../.venv/bin/python -m pytest tests/backend/test_probability_profile.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'backend.services.probability_profile'`.

- [ ] **Step 3: Implement the pure profile generator**

Create `python/backend/services/probability_profile.py`:

```python
from dataclasses import dataclass
from typing import Literal

from backend.services.distributions import LognormalDistribution


CORE_LOWER_PROBABILITY = 0.01
CORE_UPPER_PROBABILITY = 0.99
PROFILE_BUCKET_COUNT = 20


@dataclass(frozen=True)
class SpotProbabilityBucket:
    lower_spot: float
    upper_spot: float
    interval_probability: float
    probability_below_upper: float
    probability_above_upper: float


@dataclass(frozen=True)
class SpotProbabilityTail:
    direction: Literal["below", "above"]
    boundary_spot: float
    probability: float


@dataclass(frozen=True)
class SpotProbabilityProfile:
    core_lower_spot: float
    core_upper_spot: float
    core_probability: float
    bucket_count: int
    intervals: tuple[SpotProbabilityBucket, ...]
    lower_tail: SpotProbabilityTail
    upper_tail: SpotProbabilityTail


def build_spot_probability_profile(
    distribution: LognormalDistribution,
) -> SpotProbabilityProfile:
    core_lower_spot = distribution.quantile(CORE_LOWER_PROBABILITY)
    core_upper_spot = distribution.quantile(CORE_UPPER_PROBABILITY)
    bucket_width = (
        core_upper_spot - core_lower_spot
    ) / PROFILE_BUCKET_COUNT
    boundaries = [
        core_lower_spot + bucket_width * index
        for index in range(PROFILE_BUCKET_COUNT)
    ]
    boundaries.append(core_upper_spot)

    intervals = []
    for lower_spot, upper_spot in zip(boundaries, boundaries[1:]):
        probability_below_lower = distribution.cdf(lower_spot)
        probability_below_upper = distribution.cdf(upper_spot)
        intervals.append(
            SpotProbabilityBucket(
                lower_spot=lower_spot,
                upper_spot=upper_spot,
                interval_probability=(
                    probability_below_upper - probability_below_lower
                ),
                probability_below_upper=probability_below_upper,
                probability_above_upper=1.0 - probability_below_upper,
            )
        )

    lower_tail_probability = distribution.cdf(core_lower_spot)
    upper_tail_probability = 1.0 - distribution.cdf(core_upper_spot)
    return SpotProbabilityProfile(
        core_lower_spot=core_lower_spot,
        core_upper_spot=core_upper_spot,
        core_probability=(
            distribution.cdf(core_upper_spot)
            - distribution.cdf(core_lower_spot)
        ),
        bucket_count=PROFILE_BUCKET_COUNT,
        intervals=tuple(intervals),
        lower_tail=SpotProbabilityTail(
            direction="below",
            boundary_spot=core_lower_spot,
            probability=lower_tail_probability,
        ),
        upper_tail=SpotProbabilityTail(
            direction="above",
            boundary_spot=core_upper_spot,
            probability=upper_tail_probability,
        ),
    )
```

- [ ] **Step 4: Run the focused tests and existing distribution tests**

Run from `python/`:

```bash
../.venv/bin/python -m pytest tests/backend/test_probability_profile.py tests/backend/test_distributions.py -v
```

Expected: all tests in both files pass; no randomness or network access occurs.

- [ ] **Step 5: Commit the pure probability component**

```bash
git add python/backend/services/probability_profile.py python/tests/backend/test_probability_profile.py
git commit -m "feat: generate spot probability profiles"
```

### Task 2: No-Hedge Amount Profile and API Contract

**Files:**
- Modify: `python/backend/models.py:94-122`
- Modify: `python/backend/services/no_hedge_probability.py:5-138`
- Modify: `python/tests/backend/test_no_hedge_probability_service.py`
- Modify: `python/tests/backend/test_no_hedge_probability_api.py`
- Modify: `python/tests/backend/test_automatic_no_hedge_probability_api.py`

**Interfaces:**
- Consumes: `build_spot_probability_profile(distribution)` from Task 1 and the existing `_amount_at_spot(payload, spot)` cash-flow adapter
- Produces: `NoHedgeProbabilityProfileInterval`, `NoHedgeProbabilityProfileTail`, `NoHedgeProbabilityProfile`, and required response field `NoHedgeProbabilityResponse.probability_profile`

- [ ] **Step 1: Write failing service and API assertions**

Append to `python/tests/backend/test_no_hedge_probability_service.py`:

```python
def test_probability_profile_contains_amount_ranges_and_open_tails() -> None:
    result = calculate_no_hedge_probability(
        make_payload(),
        valuation_date=VALUATION_DATE,
    )
    profile = result.probability_profile

    assert profile.bucket_count == 20
    assert len(profile.intervals) == 20
    first = profile.intervals[0]
    assert first.minimum_amount_cny == pytest.approx(
        first.lower_spot * 1_000_000
    )
    assert first.maximum_amount_cny == pytest.approx(
        first.upper_spot * 1_000_000
    )
    assert profile.lower_tail.direction == "below"
    assert profile.lower_tail.boundary_amount_cny == pytest.approx(
        profile.lower_tail.boundary_spot * 1_000_000
    )
    assert profile.upper_tail.direction == "above"
    total = (
        profile.lower_tail.probability
        + sum(item.interval_probability for item in profile.intervals)
        + profile.upper_tail.probability
    )
    assert total == pytest.approx(1.0)
```

Add these assertions inside `test_probability_endpoint_returns_assumption_analysis()` in `python/tests/backend/test_no_hedge_probability_api.py`:

```python
    profile = body["probability_profile"]
    assert profile["bucket_count"] == 20
    assert len(profile["intervals"]) == 20
    assert profile["lower_tail"]["direction"] == "below"
    assert profile["upper_tail"]["direction"] == "above"
    assert profile["intervals"][0]["minimum_amount_cny"] < (
        profile["intervals"][0]["maximum_amount_cny"]
    )
```

Add these assertions inside `test_automatic_endpoint_needs_no_assumption_fields()` in `python/tests/backend/test_automatic_no_hedge_probability_api.py`:

```python
    assert body["probability_profile"]["bucket_count"] == 20
    assert len(body["probability_profile"]["intervals"]) == 20
    assert body["data_sources"]["forecast"]["aggregation_status"] == (
        "equal_weight_consensus"
    )
```

- [ ] **Step 2: Run the focused tests and confirm the missing response field failure**

Run from `python/`:

```bash
../.venv/bin/python -m pytest tests/backend/test_no_hedge_probability_service.py tests/backend/test_no_hedge_probability_api.py tests/backend/test_automatic_no_hedge_probability_api.py -v
```

Expected: new assertions fail because `NoHedgeProbabilityResponse` has no `probability_profile` field.

- [ ] **Step 3: Add the no-hedge response models**

Insert after `TargetProbability` in `python/backend/models.py`:

```python
class NoHedgeProbabilityProfileInterval(BaseModel):
    lower_spot: float
    upper_spot: float
    interval_probability: float
    probability_below_upper: float
    probability_above_upper: float
    minimum_amount_cny: float
    maximum_amount_cny: float


class NoHedgeProbabilityProfileTail(BaseModel):
    direction: Literal["below", "above"]
    boundary_spot: float
    probability: float
    boundary_amount_cny: float


class NoHedgeProbabilityProfile(BaseModel):
    core_lower_spot: float
    core_upper_spot: float
    core_probability: float
    bucket_count: int
    intervals: list[NoHedgeProbabilityProfileInterval]
    lower_tail: NoHedgeProbabilityProfileTail
    upper_tail: NoHedgeProbabilityProfileTail
```

Add the required field to `NoHedgeProbabilityResponse`:

```python
class NoHedgeProbabilityResponse(BaseModel):
    status: Literal["calculated"] = "calculated"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    distribution: DistributionMetadata
    result_kind: ResultKind
    expected_result: ExpectedResult
    typical_range_50: ProbabilityRange
    wide_range_90: ProbabilityRange
    target_probability: TargetProbability | None
    probability_profile: NoHedgeProbabilityProfile
```

- [ ] **Step 4: Convert the spot profile to no-hedge amount ranges**

Add these imports to `python/backend/services/no_hedge_probability.py`:

```python
from backend.models import (
    NoHedgeProbabilityProfile,
    NoHedgeProbabilityProfileInterval,
    NoHedgeProbabilityProfileTail,
)
from backend.services.probability_profile import (
    build_spot_probability_profile,
)
```

Add this helper before `calculate_no_hedge_probability()`:

```python
def _no_hedge_probability_profile(
    payload: NoHedgeProbabilityRequest,
    distribution: LognormalDistribution,
) -> NoHedgeProbabilityProfile:
    spot_profile = build_spot_probability_profile(distribution)
    intervals = []
    for interval in spot_profile.intervals:
        lower_amount = _amount_at_spot(payload, interval.lower_spot)
        upper_amount = _amount_at_spot(payload, interval.upper_spot)
        intervals.append(
            NoHedgeProbabilityProfileInterval(
                lower_spot=interval.lower_spot,
                upper_spot=interval.upper_spot,
                interval_probability=interval.interval_probability,
                probability_below_upper=(
                    interval.probability_below_upper
                ),
                probability_above_upper=(
                    interval.probability_above_upper
                ),
                minimum_amount_cny=min(lower_amount, upper_amount),
                maximum_amount_cny=max(lower_amount, upper_amount),
            )
        )

    return NoHedgeProbabilityProfile(
        core_lower_spot=spot_profile.core_lower_spot,
        core_upper_spot=spot_profile.core_upper_spot,
        core_probability=spot_profile.core_probability,
        bucket_count=spot_profile.bucket_count,
        intervals=intervals,
        lower_tail=NoHedgeProbabilityProfileTail(
            direction=spot_profile.lower_tail.direction,
            boundary_spot=spot_profile.lower_tail.boundary_spot,
            probability=spot_profile.lower_tail.probability,
            boundary_amount_cny=_amount_at_spot(
                payload,
                spot_profile.lower_tail.boundary_spot,
            ),
        ),
        upper_tail=NoHedgeProbabilityProfileTail(
            direction=spot_profile.upper_tail.direction,
            boundary_spot=spot_profile.upper_tail.boundary_spot,
            probability=spot_profile.upper_tail.probability,
            boundary_amount_cny=_amount_at_spot(
                payload,
                spot_profile.upper_tail.boundary_spot,
            ),
        ),
    )
```

Add this argument to the existing `NoHedgeProbabilityResponse(...)` construction:

```python
        probability_profile=_no_hedge_probability_profile(
            payload,
            distribution,
        ),
```

- [ ] **Step 5: Run no-hedge model, service, manual API, and automatic API tests**

Run from `python/`:

```bash
../.venv/bin/python -m pytest tests/backend/test_probability_models.py tests/backend/test_no_hedge_probability_service.py tests/backend/test_no_hedge_probability_api.py tests/backend/test_automatic_no_hedge_probability_service.py tests/backend/test_automatic_no_hedge_probability_api.py -v
```

Expected: all selected tests pass. The automatic response includes the same profile because `AutomaticNoHedgeProbabilityResponse` inherits `NoHedgeProbabilityResponse`; ING/MUFG and FRED fields remain present.

- [ ] **Step 6: Commit the no-hedge probability profile**

```bash
git add python/backend/models.py python/backend/services/no_hedge_probability.py python/tests/backend/test_no_hedge_probability_service.py python/tests/backend/test_no_hedge_probability_api.py python/tests/backend/test_automatic_no_hedge_probability_api.py
git commit -m "feat: expose no-hedge probability profiles"
```

### Task 3: Forward Strategy Amount Profile and API Contract

**Files:**
- Modify: `python/backend/forward_strategy/schemas.py:121-178`
- Modify: `python/backend/forward_strategy/probability.py:6-315`
- Modify: `python/tests/backend/test_forward_strategy_probability.py`
- Modify: `python/tests/backend/test_automatic_forward_strategy_probability_api.py`

**Interfaces:**
- Consumes: `SpotProbabilityProfile` and `build_spot_probability_profile()` from Task 1, plus existing `scenario_amounts_at_spot(payload, spot)`
- Produces: `ProfileAmountRange`, `ForwardProbabilityProfileInterval`, `ForwardProbabilityProfileTail`, `ForwardProbabilityProfile`, and required response field `ForwardStrategyProbabilityResponse.probability_profile`

- [ ] **Step 1: Write failing strategy profile tests**

Append to `python/tests/backend/test_forward_strategy_probability.py`:

```python
def test_profile_compares_no_hedge_and_strategy_on_same_spot_buckets() -> None:
    result = calculate(request())
    profile = result.probability_profile

    assert profile.bucket_count == 20
    assert len(profile.intervals) == 20
    first = profile.intervals[0]
    assert first.no_hedge.minimum_amount_cny < (
        first.no_hedge.maximum_amount_cny
    )
    assert first.forward_strategy.minimum_amount_cny < (
        first.forward_strategy.maximum_amount_cny
    )
    assert profile.lower_tail.no_hedge_amount_cny == pytest.approx(
        profile.lower_tail.boundary_spot * 1_000_000
    )
    total = (
        profile.lower_tail.probability
        + sum(item.interval_probability for item in profile.intervals)
        + profile.upper_tail.probability
    )
    assert total == pytest.approx(1.0)


def test_full_hedge_profile_has_fixed_strategy_amount() -> None:
    result = calculate(
        request(
            legs=[{"notional_usd": 1_000_000, "forward_rate": 6.80}]
        )
    )

    for interval in result.probability_profile.intervals:
        assert interval.forward_strategy.minimum_amount_cny == 6_800_000
        assert interval.forward_strategy.maximum_amount_cny == 6_800_000


def test_overhedged_profile_keeps_every_strategy_range_sorted() -> None:
    result = calculate(
        request(
            legs=[{"notional_usd": 1_500_000, "forward_rate": 6.80}]
        )
    )

    assert result.forward_strategy.coverage.status == "over_hedged"
    for interval in result.probability_profile.intervals:
        assert interval.forward_strategy.minimum_amount_cny <= (
            interval.forward_strategy.maximum_amount_cny
        )
```

Add these assertions inside `test_endpoint_returns_strategy_comparison_without_assumptions()` in `python/tests/backend/test_automatic_forward_strategy_probability_api.py`:

```python
    profile = body["probability_profile"]
    assert profile["bucket_count"] == 20
    assert len(profile["intervals"]) == 20
    assert profile["lower_tail"]["direction"] == "below"
    assert profile["upper_tail"]["direction"] == "above"
    assert set(profile["intervals"][0]) >= {
        "interval_probability",
        "probability_below_upper",
        "probability_above_upper",
        "no_hedge",
        "forward_strategy",
    }
```

- [ ] **Step 2: Run focused tests and confirm the missing strategy field failure**

Run from `python/`:

```bash
../.venv/bin/python -m pytest tests/backend/test_forward_strategy_probability.py tests/backend/test_automatic_forward_strategy_probability_api.py -v
```

Expected: new assertions fail because `ForwardStrategyProbabilityResponse` has no `probability_profile` field.

- [ ] **Step 3: Add the forward profile response models**

Insert before `ForwardStrategyProbabilityResponse` in `python/backend/forward_strategy/schemas.py`:

```python
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
```

Add the field to `ForwardStrategyProbabilityResponse`:

```python
class ForwardStrategyProbabilityResponse(BaseModel):
    status: Literal["calculated"] = "calculated"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    result_kind: ResultKind
    distribution: ForwardProbabilityDistribution
    no_hedge: StrategyProbabilityResult
    forward_strategy: ForwardStrategyProbabilityResult
    comparison: ForwardStrategyProbabilityComparison
    probability_profile: ForwardProbabilityProfile
```

- [ ] **Step 4: Map shared spot boundaries to both amount series**

Extend imports in `python/backend/forward_strategy/probability.py`:

```python
from backend.forward_strategy.schemas import (
    ForwardProbabilityProfile,
    ForwardProbabilityProfileInterval,
    ForwardProbabilityProfileTail,
    ProfileAmountRange,
)
from backend.services.probability_profile import (
    SpotProbabilityBucket,
    SpotProbabilityProfile,
    build_spot_probability_profile,
)
```

Add these helpers before `calculate_forward_strategy_probability()`:

```python
def _profile_amount_range(
    bucket: SpotProbabilityBucket,
    amounts_by_spot: dict[float, ScenarioAmounts],
    *,
    strategy: bool,
) -> ProfileAmountRange:
    lower = amounts_by_spot[bucket.lower_spot]
    upper = amounts_by_spot[bucket.upper_spot]
    values = (
        [lower.strategy_amount_cny, upper.strategy_amount_cny]
        if strategy
        else [lower.no_hedge_amount_cny, upper.no_hedge_amount_cny]
    )
    return ProfileAmountRange(
        minimum_amount_cny=min(values),
        maximum_amount_cny=max(values),
    )


def _forward_probability_profile(
    payload: ForwardStrategyProbabilityRequest,
    spot_profile: SpotProbabilityProfile,
) -> ForwardProbabilityProfile:
    boundary_spots = [spot_profile.core_lower_spot]
    boundary_spots.extend(
        interval.upper_spot for interval in spot_profile.intervals
    )
    amounts_by_spot = {
        spot: scenario_amounts_at_spot(payload, spot)
        for spot in boundary_spots
    }
    intervals = [
        ForwardProbabilityProfileInterval(
            lower_spot=interval.lower_spot,
            upper_spot=interval.upper_spot,
            interval_probability=interval.interval_probability,
            probability_below_upper=interval.probability_below_upper,
            probability_above_upper=interval.probability_above_upper,
            no_hedge=_profile_amount_range(
                interval,
                amounts_by_spot,
                strategy=False,
            ),
            forward_strategy=_profile_amount_range(
                interval,
                amounts_by_spot,
                strategy=True,
            ),
        )
        for interval in spot_profile.intervals
    ]
    lower_amounts = amounts_by_spot[spot_profile.core_lower_spot]
    upper_amounts = amounts_by_spot[spot_profile.core_upper_spot]
    return ForwardProbabilityProfile(
        core_lower_spot=spot_profile.core_lower_spot,
        core_upper_spot=spot_profile.core_upper_spot,
        core_probability=spot_profile.core_probability,
        bucket_count=spot_profile.bucket_count,
        intervals=intervals,
        lower_tail=ForwardProbabilityProfileTail(
            direction=spot_profile.lower_tail.direction,
            boundary_spot=spot_profile.lower_tail.boundary_spot,
            probability=spot_profile.lower_tail.probability,
            no_hedge_amount_cny=lower_amounts.no_hedge_amount_cny,
            forward_strategy_amount_cny=lower_amounts.strategy_amount_cny,
        ),
        upper_tail=ForwardProbabilityProfileTail(
            direction=spot_profile.upper_tail.direction,
            boundary_spot=spot_profile.upper_tail.boundary_spot,
            probability=spot_profile.upper_tail.probability,
            no_hedge_amount_cny=upper_amounts.no_hedge_amount_cny,
            forward_strategy_amount_cny=upper_amounts.strategy_amount_cny,
        ),
    )
```

After building `distribution` inside `calculate_forward_strategy_probability()`, build the shared spot profile exactly once:

```python
    spot_profile = build_spot_probability_profile(distribution)
```

Add the required response argument:

```python
        probability_profile=_forward_probability_profile(
            payload,
            spot_profile,
        ),
```

- [ ] **Step 5: Run strategy model, calculation, and automatic API tests**

Run from `python/`:

```bash
../.venv/bin/python -m pytest tests/backend/test_forward_strategy_probability_models.py tests/backend/test_forward_strategy_probability.py tests/backend/test_automatic_forward_strategy_probability_service.py tests/backend/test_automatic_forward_strategy_probability_api.py -v
```

Expected: all selected tests pass. Partial hedges have narrower strategy ranges, full hedges have fixed strategy amounts, and overhedged ranges remain ordered.

- [ ] **Step 6: Commit the forward strategy probability profile**

```bash
git add python/backend/forward_strategy/schemas.py python/backend/forward_strategy/probability.py python/tests/backend/test_forward_strategy_probability.py python/tests/backend/test_automatic_forward_strategy_probability_api.py
git commit -m "feat: expose forward strategy probability profiles"
```

### Task 4: User Documentation and Full Regression Gate

**Files:**
- Modify: `README.md:135-154`

**Interfaces:**
- Consumes: the three existing probability endpoints with their new `probability_profile` response field
- Produces: a repeatable `/docs` verification procedure and a documented explanation of interval, cumulative, and tail probabilities

- [ ] **Step 1: Add the Phase 10 manual verification section**

Append this section after the Phase 9 section in `README.md`:

````markdown
### 第十阶段：完整汇率概率剖面

现有概率响应新增 `probability_profile`，不需要用户增加输入。该字段包含 P1–P99 之间的 20 个等宽汇率区间、P1 以下的左尾风险和 P99 以上的右尾风险。

每个主要区间返回：

- 区间自身的发生概率；
- 低于和高于区间上边界的累计概率；
- 不套保人民币金额范围；
- 远期策略接口中的远期金额范围。

启动后端并在 `http://127.0.0.1:8000/docs` 中测试：

```text
POST /api/v1/analysis/no-hedge/probability
POST /api/v1/analysis/no-hedge/automatic-probability
POST /api/v1/analysis/forward-strategy/automatic-probability
```

检查 `bucket_count = 20`，`intervals` 长度为 20，且 20 个区间加左右尾部的概率合计约为 1。左右尾部是开放区间，因此只提供边界汇率、尾部概率和边界金额。

精确某一个汇率点在连续分布中的概率为零，因此系统展示“某个汇率区间的概率”，不将概率密度误称为点概率。概率剖面是对现有模型的更细展示，不代表机构预测或历史波动率本身因为区间增多而变得更准确。
````

- [ ] **Step 2: Run formatting checks and the full backend suite**

Run from the worktree root:

```bash
git diff --check
```

Expected: exit code 0 with no whitespace errors.

Run from `python/`:

```bash
../.venv/bin/python -m pytest tests -v
```

Expected: all existing 262 tests plus the new probability profile tests pass; only the already-known Starlette `httpx` deprecation warning may remain.

- [ ] **Step 3: Verify the OpenAPI response schemas expose the new field**

Run from the worktree root:

```bash
PYTHONPATH=python .venv/bin/python -c 'from backend.main import app; schemas=app.openapi()["components"]["schemas"]; names=("NoHedgeProbabilityResponse", "AutomaticNoHedgeProbabilityResponse", "ForwardStrategyProbabilityResponse", "AutomaticForwardStrategyProbabilityResponse"); assert all("probability_profile" in schemas[name]["properties"] for name in names); print("all probability profile schemas present")'
```

Expected: `all probability profile schemas present`.

- [ ] **Step 4: Inspect the final change scope**

```bash
git status --short
git diff --stat HEAD
git diff --check
```

Expected: only the files named in this plan are modified; no cache files, `.venv` files, frontend files, or external-data fixtures are tracked.

- [ ] **Step 5: Commit the documentation and final verified state**

```bash
git add README.md
git commit -m "docs: explain probability profile responses"
```

- [ ] **Step 6: Run a final post-commit verification**

Run from `python/`:

```bash
../.venv/bin/python -m pytest tests -q
```

Then run from the worktree root:

```bash
git status --short --branch
```

Expected: the full suite passes and the working tree is clean on `phase-10-probability-profile`.
