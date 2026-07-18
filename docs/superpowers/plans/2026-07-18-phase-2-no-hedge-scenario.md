# Phase 2 No-Hedge Scenario Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend endpoint that calculates the USD/CNY no-hedge amount for one assumed maturity spot and optionally compares it with the user's target.

**Architecture:** Extend the existing Pydantic contracts with explicit scenario and result models, then add a pure `Decimal`-based service that owns all money and target-comparison rules. A thin FastAPI route calls that service; it does not fetch external data or contain financial formulas.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, `decimal.Decimal`, pytest, HTTPX TestClient

## Global Constraints

- Currency pair is exactly `USD/CNY`, quoted as CNY per 1 USD.
- Supported exposure types are future USD receivable, future USD payable, and currently held USD.
- The assumed maturity spot is required and must be greater than zero.
- The assumed spot is a scenario parameter, not a forecast; every response must say `scenario_type: assumption` and `is_forecast: false`.
- USD receivable and USD holding produce CNY proceeds; USD payable produces a CNY cost.
- For proceeds, meeting the target means result greater than or equal to target; for cost, meeting the target means result less than or equal to target.
- If no target is supplied, the target comparison is `null`.
- Formal multiplication and rounding use `Decimal` with `ROUND_HALF_UP` to CNY 0.01; response numbers are already rounded to cents.
- No external data, probability, market reference, forward, option, database, authentication, or frontend code is included.
- Existing Phase 1 validation and existing `python/hedging/` behavior must remain unchanged.
- Use test-driven development: fail first, implement the minimum, pass, then commit.

---

## File Structure

```text
python/
├── backend/
│   ├── errors.py                    Add assumed-spot Chinese error copy
│   ├── main.py                      Register the analysis route
│   ├── models.py                    Add request and response contracts
│   ├── routes/
│   │   └── analysis.py              No-hedge scenario HTTP endpoint
│   └── services/
│       ├── __init__.py              Package marker
│       └── no_hedge.py              Pure Decimal calculation service
└── tests/backend/
    ├── test_no_hedge_models.py      Request contract tests
    ├── test_no_hedge_service.py     Formula and target-rule tests
    └── test_no_hedge_api.py         HTTP contract and Chinese-error tests
```

`README.md` gains the manual `/docs` check for this endpoint.

---

### Task 1: No-Hedge Scenario Request and Response Contracts

**Files:**
- Modify: `python/backend/models.py`
- Create: `python/tests/backend/test_no_hedge_models.py`

**Interfaces:**
- Consumes: existing `AnalysisInput` and `ExposureType` from `backend.models`.
- Produces: `NoHedgeScenarioRequest`, `ScenarioMetadata`, `ResultKind`, `DifferenceType`, `TargetComparison`, and `NoHedgeScenarioResponse` for Task 2 and Task 3.

- [ ] **Step 1: Write the failing request-model tests**

Create `python/tests/backend/test_no_hedge_models.py`:

```python
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.models import NoHedgeScenarioRequest


def future_date() -> date:
    return date.today() + timedelta(days=90)


def test_no_hedge_request_accepts_positive_assumed_spot() -> None:
    payload = NoHedgeScenarioRequest(
        exposure_type="usd_receivable",
        notional_usd=1_000_000,
        maturity_date=future_date(),
        target_cny=6_800_000,
        assumed_maturity_spot=6.75,
    )

    assert payload.currency_pair == "USD/CNY"
    assert payload.assumed_maturity_spot == 6.75


@pytest.mark.parametrize("assumed_spot", [0, -1])
def test_no_hedge_request_rejects_non_positive_assumed_spot(
    assumed_spot: float,
) -> None:
    with pytest.raises(ValidationError):
        NoHedgeScenarioRequest(
            exposure_type="usd_receivable",
            notional_usd=1_000_000,
            maturity_date=future_date(),
            assumed_maturity_spot=assumed_spot,
        )
```

- [ ] **Step 2: Run the focused test and verify the new model is missing**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_no_hedge_models.py -v
```

Expected: collection fails with `ImportError: cannot import name 'NoHedgeScenarioRequest'`.

- [ ] **Step 3: Add the request and response contracts**

Append to `python/backend/models.py`:

```python
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
```

- [ ] **Step 4: Run model and Phase 1 contract tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest \
  python/tests/backend/test_no_hedge_models.py \
  python/tests/backend/test_models.py -v
```

Expected: `11 passed`.

- [ ] **Step 5: Commit the contracts**

```bash
git add python/backend/models.py python/tests/backend/test_no_hedge_models.py
git commit -m "feat: define no-hedge scenario contracts"
```

---

### Task 2: Pure Decimal No-Hedge Calculation Service

**Files:**
- Create: `python/backend/services/__init__.py`
- Create: `python/backend/services/no_hedge.py`
- Create: `python/tests/backend/test_no_hedge_service.py`

**Interfaces:**
- Consumes: `NoHedgeScenarioRequest` from Task 1.
- Produces: `calculate_no_hedge_scenario(payload: NoHedgeScenarioRequest) -> NoHedgeScenarioResponse` for the HTTP route in Task 3.

- [ ] **Step 1: Write failing tests for exposure meaning and amount**

Create `python/tests/backend/test_no_hedge_service.py`:

```python
from datetime import date, timedelta

import pytest

from backend.models import (
    DifferenceType,
    NoHedgeScenarioRequest,
    ResultKind,
)
from backend.services.no_hedge import calculate_no_hedge_scenario


def make_payload(
    *,
    exposure_type: str = "usd_receivable",
    notional_usd: float = 1_000_000,
    assumed_spot: float = 6.75,
    target_cny: float | None = 6_800_000,
) -> NoHedgeScenarioRequest:
    return NoHedgeScenarioRequest(
        exposure_type=exposure_type,
        notional_usd=notional_usd,
        maturity_date=date.today() + timedelta(days=90),
        target_cny=target_cny,
        assumed_maturity_spot=assumed_spot,
    )


@pytest.mark.parametrize(
    ("exposure_type", "expected_kind"),
    [
        ("usd_receivable", ResultKind.CNY_PROCEEDS),
        ("usd_holding", ResultKind.CNY_PROCEEDS),
        ("usd_payable", ResultKind.CNY_COST),
    ],
)
def test_calculation_assigns_business_meaning(
    exposure_type: str,
    expected_kind: ResultKind,
) -> None:
    result = calculate_no_hedge_scenario(
        make_payload(exposure_type=exposure_type)
    )

    assert result.result_kind is expected_kind
    assert result.no_hedge_amount_cny == 6_750_000.00
    assert result.scenario.scenario_type == "assumption"
    assert result.scenario.is_forecast is False


@pytest.mark.parametrize(
    (
        "exposure_type",
        "assumed_spot",
        "target_cny",
        "target_met",
        "difference_cny",
        "difference_type",
    ),
    [
        (
            "usd_receivable",
            6.80,
            6_800_000,
            True,
            0.00,
            DifferenceType.ON_TARGET,
        ),
        (
            "usd_receivable",
            6.90,
            6_800_000,
            True,
            100_000.00,
            DifferenceType.SURPLUS,
        ),
        (
            "usd_holding",
            6.70,
            6_800_000,
            False,
            100_000.00,
            DifferenceType.SHORTFALL,
        ),
        (
            "usd_payable",
            6.70,
            6_800_000,
            True,
            100_000.00,
            DifferenceType.COST_SAVING,
        ),
        (
            "usd_payable",
            6.90,
            6_800_000,
            False,
            100_000.00,
            DifferenceType.EXCESS_COST,
        ),
    ],
)
def test_calculation_compares_target_by_exposure_direction(
    exposure_type: str,
    assumed_spot: float,
    target_cny: float,
    target_met: bool,
    difference_cny: float,
    difference_type: DifferenceType,
) -> None:
    result = calculate_no_hedge_scenario(
        make_payload(
            exposure_type=exposure_type,
            assumed_spot=assumed_spot,
            target_cny=target_cny,
        )
    )

    assert result.target_comparison is not None
    assert result.target_comparison.target_met is target_met
    assert result.target_comparison.difference_cny == difference_cny
    assert result.target_comparison.difference_type is difference_type


def test_calculation_omits_comparison_without_target() -> None:
    result = calculate_no_hedge_scenario(make_payload(target_cny=None))

    assert result.target_comparison is None


def test_calculation_rounds_half_up_to_cny_cent() -> None:
    result = calculate_no_hedge_scenario(
        make_payload(
            notional_usd=1.005,
            assumed_spot=1,
            target_cny=None,
        )
    )

    assert result.no_hedge_amount_cny == 1.01
```

- [ ] **Step 2: Run the service tests and verify the service is missing**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_no_hedge_service.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'backend.services'`.

- [ ] **Step 3: Implement the pure calculation service**

Create an empty `python/backend/services/__init__.py`.

Create `python/backend/services/no_hedge.py`:

```python
from decimal import Decimal, ROUND_HALF_UP

from backend.models import (
    DifferenceType,
    ExposureType,
    NoHedgeScenarioRequest,
    NoHedgeScenarioResponse,
    ResultKind,
    ScenarioMetadata,
    TargetComparison,
)


CNY_CENT = Decimal("0.01")


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _cny(value: Decimal) -> Decimal:
    return value.quantize(CNY_CENT, rounding=ROUND_HALF_UP)


def _target_comparison(
    *,
    exposure_type: ExposureType,
    amount_cny: Decimal,
    target_cny: float | None,
) -> TargetComparison | None:
    if target_cny is None:
        return None

    target = _cny(_decimal(target_cny))
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


def calculate_no_hedge_scenario(
    payload: NoHedgeScenarioRequest,
) -> NoHedgeScenarioResponse:
    amount_cny = _cny(
        _decimal(payload.notional_usd)
        * _decimal(payload.assumed_maturity_spot)
    )
    result_kind = (
        ResultKind.CNY_COST
        if payload.exposure_type is ExposureType.USD_PAYABLE
        else ResultKind.CNY_PROCEEDS
    )

    return NoHedgeScenarioResponse(
        scenario=ScenarioMetadata(
            assumed_maturity_spot=payload.assumed_maturity_spot,
        ),
        result_kind=result_kind,
        no_hedge_amount_cny=float(amount_cny),
        target_comparison=_target_comparison(
            exposure_type=payload.exposure_type,
            amount_cny=amount_cny,
            target_cny=payload.target_cny,
        ),
    )
```

- [ ] **Step 4: Run the focused service tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_no_hedge_service.py -v
```

Expected: `10 passed`.

- [ ] **Step 5: Run all backend tests to catch contract regressions**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend -v
```

Expected: `29 passed` at this point.

- [ ] **Step 6: Commit the pure service**

```bash
git add \
  python/backend/services/__init__.py \
  python/backend/services/no_hedge.py \
  python/tests/backend/test_no_hedge_service.py
git commit -m "feat: calculate no-hedge scenario results"
```

---

### Task 3: No-Hedge HTTP Endpoint, Chinese Error, and Manual Check

**Files:**
- Modify: `python/backend/errors.py`
- Modify: `python/backend/main.py`
- Create: `python/backend/routes/analysis.py`
- Create: `python/tests/backend/test_no_hedge_api.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `calculate_no_hedge_scenario()` from Task 2 and the Task 1 request/response models.
- Produces: `POST /api/v1/analysis/no-hedge/scenario` with stable success and `validation_error` responses.

- [ ] **Step 1: Write failing endpoint tests**

Create `python/tests/backend/test_no_hedge_api.py`:

```python
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def valid_payload() -> dict[str, object]:
    return {
        "currency_pair": "USD/CNY",
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": (date.today() + timedelta(days=90)).isoformat(),
        "target_cny": 6_800_000,
        "assumed_maturity_spot": 6.75,
    }


def test_no_hedge_endpoint_returns_assumption_result() -> None:
    response = client.post(
        "/api/v1/analysis/no-hedge/scenario",
        json=valid_payload(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "calculated",
        "quote_convention": "CNY per 1 USD",
        "scenario": {
            "scenario_type": "assumption",
            "is_forecast": False,
            "assumed_maturity_spot": 6.75,
        },
        "result_kind": "cny_proceeds",
        "no_hedge_amount_cny": 6_750_000.0,
        "target_comparison": {
            "target_cny": 6_800_000.0,
            "target_met": False,
            "difference_cny": 50_000.0,
            "difference_type": "shortfall",
        },
    }


def test_no_hedge_endpoint_allows_target_to_be_omitted() -> None:
    payload = valid_payload()
    payload.pop("target_cny")

    response = client.post(
        "/api/v1/analysis/no-hedge/scenario",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["target_comparison"] is None


@pytest.mark.parametrize("assumed_spot", [0, -1])
def test_no_hedge_endpoint_returns_friendly_spot_error(
    assumed_spot: float,
) -> None:
    payload = valid_payload()
    payload["assumed_maturity_spot"] = assumed_spot

    response = client.post(
        "/api/v1/analysis/no-hedge/scenario",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "输入内容有误",
            "fields": [
                {
                    "field": "assumed_maturity_spot",
                    "message": "假设到期汇率必须大于 0",
                }
            ],
        }
    }
```

- [ ] **Step 2: Run the endpoint tests and verify the route is missing**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_no_hedge_api.py -v
```

Expected: four failures because the endpoint returns `404`.

- [ ] **Step 3: Add the stable Chinese validation message**

Add this entry to `FIELD_MESSAGES` in `python/backend/errors.py`:

```python
"assumed_maturity_spot": "假设到期汇率必须大于 0",
```

- [ ] **Step 4: Add the analysis route**

Create `python/backend/routes/analysis.py`:

```python
from fastapi import APIRouter

from backend.models import NoHedgeScenarioRequest, NoHedgeScenarioResponse
from backend.services.no_hedge import calculate_no_hedge_scenario


router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.post(
    "/no-hedge/scenario",
    response_model=NoHedgeScenarioResponse,
)
def no_hedge_scenario(
    payload: NoHedgeScenarioRequest,
) -> NoHedgeScenarioResponse:
    return calculate_no_hedge_scenario(payload)
```

- [ ] **Step 5: Register the route in the FastAPI app**

Add this import to `python/backend/main.py`:

```python
from backend.routes.analysis import router as analysis_router
```

Register it before the existing input router inside `create_app()`:

```python
app.include_router(analysis_router)
app.include_router(inputs_router)
```

- [ ] **Step 6: Run endpoint and backend tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend -v
```

Expected: `33 passed`.

- [ ] **Step 7: Add the beginner-friendly manual test to README**

Append under `## 第一阶段 Python 后端` in `README.md`:

````markdown

### 第二阶段：不套保单一情景

启动后端并打开 `http://127.0.0.1:8000/docs`，展开：

```text
POST /api/v1/analysis/no-hedge/scenario
```

点击 `Try it out`，输入：

```json
{
  "currency_pair": "USD/CNY",
  "exposure_type": "usd_receivable",
  "notional_usd": 1000000,
  "maturity_date": "2030-12-31",
  "target_cny": 6800000,
  "assumed_maturity_spot": 6.75
}
```

返回结果应显示不套保金额为 `6750000.0`、未达标、距离目标 `50000.0`，并明确标记该汇率是假设而不是预测。
````

- [ ] **Step 8: Run the full Python regression suite**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests -v
```

Expected: `44 passed`.

- [ ] **Step 9: Start the real server and manually verify both paths**

Start:

```bash
.venv/bin/python -m uvicorn backend.main:app --app-dir python
```

Check the success path in another terminal:

```bash
curl --silent --request POST \
  http://127.0.0.1:8000/api/v1/analysis/no-hedge/scenario \
  --header 'Content-Type: application/json' \
  --data '{
    "currency_pair": "USD/CNY",
    "exposure_type": "usd_receivable",
    "notional_usd": 1000000,
    "maturity_date": "2030-12-31",
    "target_cny": 6800000,
    "assumed_maturity_spot": 6.75
  }'
```

Expected: HTTP JSON contains `"no_hedge_amount_cny":6750000.0`, `"target_met":false`, and `"difference_type":"shortfall"`.

Check the invalid path:

```bash
curl --silent --request POST \
  http://127.0.0.1:8000/api/v1/analysis/no-hedge/scenario \
  --header 'Content-Type: application/json' \
  --data '{
    "currency_pair": "USD/CNY",
    "exposure_type": "usd_receivable",
    "notional_usd": 1000000,
    "maturity_date": "2030-12-31",
    "assumed_maturity_spot": 0
  }'
```

Expected: HTTP JSON contains `"message":"假设到期汇率必须大于 0"`.

- [ ] **Step 10: Commit the completed Phase 2 feature**

```bash
git add \
  README.md \
  python/backend/errors.py \
  python/backend/main.py \
  python/backend/routes/analysis.py \
  python/tests/backend/test_no_hedge_api.py
git commit -m "feat: expose no-hedge scenario analysis"
```

---

## Phase 2 Acceptance Checklist

- [ ] One positive assumed maturity spot produces one no-hedge CNY amount.
- [ ] USD receivable and holding return `cny_proceeds`; USD payable returns `cny_cost`.
- [ ] Every response identifies the scenario as an assumption and not a forecast.
- [ ] Proceeds targets use `result >= target`; cost targets use `result <= target`.
- [ ] All five difference types are covered: `on_target`, `surplus`, `shortfall`, `cost_saving`, and `excess_cost`.
- [ ] Missing targets produce `target_comparison: null`.
- [ ] Money is rounded half-up to CNY 0.01 with Decimal arithmetic.
- [ ] Non-positive assumed spots return the stable Chinese error.
- [ ] No market data, forecast, probability, hedge strategy, database, authentication, or frontend code was added.
- [ ] All existing backend and hedging tests remain green.
- [ ] README commands work from the repository root.
