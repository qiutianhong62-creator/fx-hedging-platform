# 第六阶段：不套保概率自动分析实施计划

> **给执行者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐步实施。步骤使用复选框（`- [ ]`）跟踪。

**目标：** 新增一个接口，自动把 ING 的 USD/CNY 预计到期汇率和 FRED 历史波动率交给现有不套保概率模型。

**架构：** 原手动概率接口保持不变。新的连接服务调用现有预测和市场历史服务，将输出转换为现有概率输入，只调用一次概率计算，并把两类数据来源附在结果中。

**技术：** Python 3.12、FastAPI、Pydantic 2、pytest、FastAPI `TestClient`、现有 ING/FRED 读取模块及对数正态概率引擎。

## 全局约束

- 货币对仍为 `USD/CNY`，报价方式为 `CNY per 1 USD`。
- 新增 `POST /api/v1/analysis/no-hedge/automatic-probability`，不修改手动接口路径。
- 自动请求只接受现有基础敞口字段；`target_cny` 仍然可选。
- 预计汇率来自 `MaturityForecastService`，历史年化波动率来自 `MarketHistoryService`。
- 概率期限使用预测结果中的 `valuation_date` 计算。
- 不复制金额、区间、达标概率、ING、FRED、新鲜度或缓存逻辑。
- 不使用猜测汇率、默认波动率或隐藏的假设备用值。
- 预测和市场数据错误保留现有错误编号和 HTTP 状态。
- 手动接口必须保持 `source_type: assumption` 和 `is_market_forecast: false`。
- 自动接口必须返回 `source_type: market_data`、`is_market_forecast: true` 及完整 ING/FRED 来源。
- FRED 波动率必须明确标记为历史数据，不能说成未来波动率预测。
- 自动化测试不访问真实 ING 或 FRED 网站。
- 不包含新机构、加权、前端、数据库、调度器、套保工具或新依赖。

---

## 文件分工

- 修改 `python/backend/models.py`：让概率分布说明同时支持人工假设和市场数据。
- 修改 `python/backend/services/no_hedge_probability.py`：支持显式传入数据来源标记，同时保留手动默认值。
- 新建 `python/backend/automatic_analysis/__init__.py`：自动分析模块标记。
- 新建 `python/backend/automatic_analysis/schemas.py`：自动结果及数据来源模型。
- 新建 `python/backend/automatic_analysis/service.py`：连接预测、历史和概率服务。
- 修改 `python/backend/routes/analysis.py`：开放新依赖和接口。
- 修改 `python/tests/backend/test_no_hedge_probability_service.py`：验证默认标记和自动覆盖。
- 新建 `python/tests/backend/test_automatic_no_hedge_probability_service.py`：验证连接逻辑和错误传递。
- 新建 `python/tests/backend/test_automatic_no_hedge_probability_api.py`：验证 HTTP 格式和依赖连接。

---

### 任务 1：让现有概率引擎能标记自动数据

**文件：**
- 修改：`python/backend/models.py`
- 修改：`python/backend/services/no_hedge_probability.py`
- 修改：`python/tests/backend/test_no_hedge_probability_service.py`

**接口：**
- 输入：现有 `NoHedgeProbabilityRequest` 及 `calculate_no_hedge_probability` 参数。
- 输出：支持 `calculate_no_hedge_probability(..., source_type="market_data", is_market_forecast=True)`，同时不改变当前默认值。

- [ ] **步骤 1：先写一个必然失败的“数据来源覆盖”测试**

在 `python/tests/backend/test_no_hedge_probability_service.py` 末尾增加：

```python
def test_probability_analysis_can_mark_automatic_market_inputs() -> None:
    result = calculate_no_hedge_probability(
        make_payload(),
        valuation_date=VALUATION_DATE,
        source_type="market_data",
        is_market_forecast=True,
    )

    assert result.distribution.source_type == "market_data"
    assert result.distribution.is_market_forecast is True
```

- [ ] **步骤 2：运行聚焦测试，确认因缺少新参数而失败**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_no_hedge_probability_service.py::test_probability_analysis_can_mark_automatic_market_inputs -v
```

预期：失败，原因是 `calculate_no_hedge_probability` 尚不接受 `source_type` 和 `is_market_forecast`。

- [ ] **步骤 3：扩展概率分布说明，不改变默认值**

在 `python/backend/models.py` 中，将 `DistributionMetadata` 中两个固定字段替换为：

```python
class DistributionMetadata(BaseModel):
    model_type: Literal["lognormal"] = "lognormal"
    source_type: Literal["assumption", "market_data"] = "assumption"
    is_market_forecast: bool = False
    assumed_expected_maturity_spot: float
    assumed_annualized_volatility_pct: float
    horizon_days: int
```

本阶段保留现有字段名，以确保手动接口输出完全兼容。

- [ ] **步骤 4：让计算器传递明确的数据来源标记**

在 `python/backend/services/no_hedge_probability.py` 中增加：

```python
from typing import Literal
```

将函数签名改为：

```python
def calculate_no_hedge_probability(
    payload: NoHedgeProbabilityRequest,
    *,
    valuation_date: date | None = None,
    source_type: Literal["assumption", "market_data"] = "assumption",
    is_market_forecast: bool = False,
) -> NoHedgeProbabilityResponse:
```

构造 `DistributionMetadata` 时传入这两个值：

```python
        distribution=DistributionMetadata(
            source_type=source_type,
            is_market_forecast=is_market_forecast,
            assumed_expected_maturity_spot=(
                payload.assumed_expected_maturity_spot
            ),
            assumed_annualized_volatility_pct=(
                payload.assumed_annualized_volatility_pct
            ),
            horizon_days=distribution.horizon_days,
        ),
```

- [ ] **步骤 5：运行概率服务和手动接口测试**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_no_hedge_probability_service.py tests/backend/test_no_hedge_probability_api.py -v
```

预期：所有测试通过；原测试继续证明手动路径返回 `assumption` 和 `false`。

- [ ] **步骤 6：保存数据来源标记功能**

```bash
git add python/backend/models.py python/backend/services/no_hedge_probability.py python/tests/backend/test_no_hedge_probability_service.py
git commit -m "feat: describe automatic probability inputs"
```

---

### 任务 2：连接 ING、FRED 和现有概率计算

**文件：**
- 新建：`python/backend/automatic_analysis/__init__.py`
- 新建：`python/backend/automatic_analysis/schemas.py`
- 新建：`python/backend/automatic_analysis/service.py`
- 新建：`python/tests/backend/test_automatic_no_hedge_probability_service.py`

**接口：**
- 输入：`AnalysisInput`、`MaturityForecastService.get_estimate(date)`、`MarketHistoryService.get_summary()` 及任务 1 扩展后的概率计算器。
- 输出：`AutomaticNoHedgeProbabilityService.calculate(payload) -> AutomaticNoHedgeProbabilityResponse`。

- [ ] **步骤 1：先写必然失败的连接服务测试**

新建 `python/tests/backend/test_automatic_no_hedge_probability_service.py`：

```python
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.automatic_analysis.service import (
    AutomaticNoHedgeProbabilityService,
)
from backend.forecast.errors import ForecastSourceUnavailableError
from backend.forecast.schemas import MaturityForecastResponse
from backend.market.errors import MarketDataUnavailableError
from backend.market.schemas import MarketHistorySummaryResponse
from backend.models import AnalysisInput


VALUATION_DATE = date.today()
MATURITY_DATE = VALUATION_DATE + timedelta(days=180)


def forecast_result() -> MaturityForecastResponse:
    return MaturityForecastResponse.model_validate(
        {
            "valuation_date": VALUATION_DATE,
            "maturity_date": MATURITY_DATE,
            "expected_maturity_spot": 6.72,
            "matching": {
                "method": "interpolated",
                "is_system_estimate": True,
                "day_weight": 0.5,
                "anchors": [
                    {"source": "ING", "date": "2026-09-30", "spot": 6.74},
                    {"source": "ING", "date": "2026-12-31", "spot": 6.70},
                ],
            },
            "sources": [
                {
                    "source_updated_date": "2026-07-16",
                    "source_url": "https://think.ing.com/forecasts/",
                    "forecast_points": [
                        {"date": "2026-09-30", "spot": 6.74},
                        {"date": "2026-12-31", "spot": 6.70},
                    ],
                    "cache_status": "daily_cache",
                    "fetched_at_utc": "2026-07-18T10:00:00Z",
                    "cache_age_hours": 2.0,
                    "is_stale": False,
                }
            ],
            "limitations": ["单一机构试验"],
        }
    )


def market_result() -> MarketHistorySummaryResponse:
    return MarketHistorySummaryResponse.model_validate(
        {
            "market_reference": {
                "spot": 6.7766,
                "observation_date": "2026-07-10",
            },
            "historical_volatility": {
                "annualized_volatility_pct": 4.2,
                "window_start": "2025-07-10",
                "window_end": "2026-07-10",
                "observation_count": 250,
                "return_count": 249,
            },
            "source": {
                "fetched_at_utc": "2026-07-18T10:00:00Z",
                "cache_status": "daily_cache",
                "cache_age_hours": 2.0,
                "data_age_days": 8,
                "is_stale": False,
            },
        }
    )


class FakeForecastService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[date] = []

    def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
        self.calls.append(maturity_date)
        if self.error is not None:
            raise self.error
        return forecast_result()


class FakeMarketService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def get_summary(self) -> MarketHistorySummaryResponse:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return market_result()


def input_payload(target_cny: float | None = 6_800_000) -> AnalysisInput:
    return AnalysisInput(
        exposure_type="usd_receivable",
        notional_usd=1_000_000,
        maturity_date=MATURITY_DATE,
        target_cny=target_cny,
    )


def test_automatic_analysis_uses_ing_spot_and_fred_volatility() -> None:
    forecast = FakeForecastService()
    market = FakeMarketService()
    service = AutomaticNoHedgeProbabilityService(
        forecast_service=forecast,
        market_history_service=market,
    )

    result = service.calculate(input_payload())

    assert forecast.calls == [MATURITY_DATE]
    assert market.calls == 1
    assert result.expected_result.spot == 6.72
    assert result.expected_result.amount_cny == 6_720_000
    assert result.distribution.assumed_expected_maturity_spot == 6.72
    assert result.distribution.assumed_annualized_volatility_pct == 4.2
    assert result.distribution.horizon_days == 180
    assert result.distribution.source_type == "market_data"
    assert result.distribution.is_market_forecast is True
    assert result.target_probability is not None
    assert result.data_sources.forecast == forecast_result()
    assert result.data_sources.market_history == market_result()


def test_automatic_analysis_allows_target_to_be_omitted() -> None:
    result = AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(),
        market_history_service=FakeMarketService(),
    ).calculate(input_payload(target_cny=None))

    assert result.target_probability is None


def test_forecast_failure_stops_before_market_lookup() -> None:
    market = FakeMarketService()
    service = AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(
            error=ForecastSourceUnavailableError()
        ),
        market_history_service=market,
    )

    with pytest.raises(ForecastSourceUnavailableError):
        service.calculate(input_payload())

    assert market.calls == 0


def test_market_failure_is_not_replaced_with_a_default() -> None:
    service = AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(),
        market_history_service=FakeMarketService(
            error=MarketDataUnavailableError()
        ),
    )

    with pytest.raises(MarketDataUnavailableError):
        service.calculate(input_payload())
```

- [ ] **步骤 2：运行测试，确认因自动分析模块尚不存在而失败**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_automatic_no_hedge_probability_service.py -v
```

预期：测试收集失败，因为 `backend.automatic_analysis` 尚不存在。

- [ ] **步骤 3：定义自动分析响应模型**

新建空文件 `python/backend/automatic_analysis/__init__.py`。

新建 `python/backend/automatic_analysis/schemas.py`：

```python
from pydantic import BaseModel

from backend.forecast.schemas import MaturityForecastResponse
from backend.market.schemas import MarketHistorySummaryResponse
from backend.models import NoHedgeProbabilityResponse


class AutomaticAnalysisDataSources(BaseModel):
    forecast: MaturityForecastResponse
    market_history: MarketHistorySummaryResponse


class AutomaticNoHedgeProbabilityResponse(NoHedgeProbabilityResponse):
    data_sources: AutomaticAnalysisDataSources
```

- [ ] **步骤 4：实现自动连接服务**

新建 `python/backend/automatic_analysis/service.py`：

```python
from datetime import date
from typing import Protocol

from backend.automatic_analysis.schemas import (
    AutomaticAnalysisDataSources,
    AutomaticNoHedgeProbabilityResponse,
)
from backend.forecast.schemas import MaturityForecastResponse
from backend.market.schemas import MarketHistorySummaryResponse
from backend.models import AnalysisInput, NoHedgeProbabilityRequest
from backend.services.no_hedge_probability import (
    calculate_no_hedge_probability,
)


class ForecastLookup(Protocol):
    def get_estimate(
        self,
        maturity_date: date,
    ) -> MaturityForecastResponse: ...


class MarketHistoryLookup(Protocol):
    def get_summary(self) -> MarketHistorySummaryResponse: ...


class AutomaticNoHedgeProbabilityService:
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
        payload: AnalysisInput,
    ) -> AutomaticNoHedgeProbabilityResponse:
        forecast = self._forecast_service.get_estimate(payload.maturity_date)
        market_history = self._market_history_service.get_summary()
        probability_input = NoHedgeProbabilityRequest(
            **payload.model_dump(),
            assumed_expected_maturity_spot=(
                forecast.expected_maturity_spot
            ),
            assumed_annualized_volatility_pct=(
                market_history.historical_volatility.annualized_volatility_pct
            ),
        )
        analysis = calculate_no_hedge_probability(
            probability_input,
            valuation_date=forecast.valuation_date,
            source_type="market_data",
            is_market_forecast=True,
        )
        return AutomaticNoHedgeProbabilityResponse(
            **analysis.model_dump(),
            data_sources=AutomaticAnalysisDataSources(
                forecast=forecast,
                market_history=market_history,
            ),
        )
```

- [ ] **步骤 5：运行自动服务及现有概率计算测试**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_automatic_no_hedge_probability_service.py tests/backend/test_no_hedge_probability_service.py -v
```

预期：所有连接测试通过，现有概率数学测试仍然通过。

- [ ] **步骤 6：保存自动连接服务**

```bash
git add python/backend/automatic_analysis python/tests/backend/test_automatic_no_hedge_probability_service.py
git commit -m "feat: combine forecast and market probability inputs"
```

---

### 任务 3：开放自动概率接口

**文件：**
- 修改：`python/backend/routes/analysis.py`
- 新建：`python/tests/backend/test_automatic_no_hedge_probability_api.py`

**接口：**
- 输入：`AnalysisInput`、`AutomaticNoHedgeProbabilityService` 及现有 ING/FRED 缓存路由依赖。
- 输出：`POST /api/v1/analysis/no-hedge/automatic-probability`。

- [ ] **步骤 1：先写必然失败的接口测试**

新建 `python/tests/backend/test_automatic_no_hedge_probability_api.py`：

```python
from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend.automatic_analysis.service import (
    AutomaticNoHedgeProbabilityService,
)
from backend.forecast.errors import ForecastSourceUnavailableError
from backend.main import app
from backend.routes.analysis import (
    get_automatic_no_hedge_probability_service,
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
    }


def automatic_service() -> AutomaticNoHedgeProbabilityService:
    return AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(),
        market_history_service=FakeMarketService(),
    )


def test_automatic_endpoint_needs_no_assumption_fields() -> None:
    app.dependency_overrides[
        get_automatic_no_hedge_probability_service
    ] = automatic_service
    try:
        response = client.post(
            "/api/v1/analysis/no-hedge/automatic-probability",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["distribution"]["source_type"] == "market_data"
    assert body["distribution"]["is_market_forecast"] is True
    assert body["distribution"]["assumed_expected_maturity_spot"] == 6.72
    assert body["distribution"]["assumed_annualized_volatility_pct"] == 4.2
    assert body["data_sources"]["forecast"]["sources"][0][
        "institution"
    ] == "ING"
    assert body["data_sources"]["market_history"]["source"][
        "provider"
    ] == "FRED"


def test_automatic_endpoint_keeps_forecast_error_contract() -> None:
    app.dependency_overrides[
        get_automatic_no_hedge_probability_service
    ] = lambda: AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(
            error=ForecastSourceUnavailableError()
        ),
        market_history_service=FakeMarketService(),
    )
    try:
        response = client.post(
            "/api/v1/analysis/no-hedge/automatic-probability",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == (
        "forecast_source_unavailable"
    )
```

- [ ] **步骤 2：运行接口测试，确认因路由依赖尚不存在而失败**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_automatic_no_hedge_probability_api.py -v
```

预期：测试收集失败，因为 `get_automatic_no_hedge_probability_service` 尚不存在。

- [ ] **步骤 3：增加自动服务依赖和接口**

在 `python/backend/routes/analysis.py` 中增加以下导入：

```python
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.automatic_analysis.schemas import (
    AutomaticNoHedgeProbabilityResponse,
)
from backend.automatic_analysis.service import (
    AutomaticNoHedgeProbabilityService,
)
from backend.routes.forecast import get_maturity_forecast_service
from backend.routes.market import get_market_history_service
```

保留现有模型导入，并增加 `AnalysisInput`。

增加可缓存的服务依赖：

```python
@lru_cache
def get_automatic_no_hedge_probability_service(
) -> AutomaticNoHedgeProbabilityService:
    return AutomaticNoHedgeProbabilityService(
        forecast_service=get_maturity_forecast_service(),
        market_history_service=get_market_history_service(),
    )
```

增加接口：

```python
@router.post(
    "/no-hedge/automatic-probability",
    response_model=AutomaticNoHedgeProbabilityResponse,
)
def automatic_no_hedge_probability(
    payload: AnalysisInput,
    service: Annotated[
        AutomaticNoHedgeProbabilityService,
        Depends(get_automatic_no_hedge_probability_service),
    ],
) -> AutomaticNoHedgeProbabilityResponse:
    return service.calculate(payload)
```

- [ ] **步骤 4：运行自动和手动接口测试**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_automatic_no_hedge_probability_api.py tests/backend/test_no_hedge_probability_api.py -v
```

预期：自动接口测试和现有手动接口测试全部通过。

- [ ] **步骤 5：运行完整后端回归测试**

运行：

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest -q
```

预期：所有现有和新增 Python 测试通过。已存在的 `StarletteDeprecationWarning` 可保留，不接受新警告。

- [ ] **步骤 6：检查改动范围并保存接口**

运行：

```bash
git diff --check
git status --short
```

预期：没有空白符错误；未保存改动中只有自动路由和接口测试。

保存：

```bash
git add python/backend/routes/analysis.py python/tests/backend/test_automatic_no_hedge_probability_api.py
git commit -m "feat: expose automatic no hedge probability"
```

---

## 最终验证清单

- [ ] 在干净分支上运行全部 Python 测试，确认零失败。
- [ ] 确认原手动接口测试仍断言 `source_type: assumption` 和 `is_market_forecast: false`。
- [ ] 确认自动请求不提供任何假设字段也能成功。
- [ ] 确认自动结果使用依赖返回的精确 ING 预计汇率和 FRED 历史年化波动率。
- [ ] 确认预测结果中的 `valuation_date` 决定 `horizon_days`。
- [ ] 确认 `data_sources` 同时包含 ING 和 FRED 来源。
- [ ] 确认预测或市场数据错误不会被替换为默认值。
- [ ] 确认 `python/requirements.txt` 未改动。
- [ ] 确认运行缓存文件仍被 Git 忽略，没有进入待提交列表。
- [ ] 使用可支持的到期日真实调用一次 `POST /api/v1/analysis/no-hedge/automatic-probability`，检查完整 ING + FRED + 概率链路。
- [ ] 手工验证真实结果中 `expected_result.amount_cny = notional_usd * expected_result.spot`。
- [ ] 确认 `git diff --check` 无错且功能分支没有未保存改动。
