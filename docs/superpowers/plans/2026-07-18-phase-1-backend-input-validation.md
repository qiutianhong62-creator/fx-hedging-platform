# Phase 1 Backend Input Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the smallest working Python backend that starts successfully, accepts a USD/CNY exposure input, normalizes valid data, and returns clear Chinese validation errors for invalid data.

**Architecture:** Add a focused FastAPI package under `python/backend/` without touching the existing strategy calculations. The package exposes a health endpoint and one versioned validation endpoint; Pydantic owns input parsing, while a separate error adapter converts technical validation failures into stable user-facing responses.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Uvicorn, pytest, HTTPX TestClient

## Global Constraints

- This plan implements only Phase 1 from `docs/superpowers/specs/2026-07-18-fx-hedging-backend-design.md`.
- Currency pair is exactly `USD/CNY`, quoted as CNY per 1 USD.
- Supported exposure types are future USD receivable, future USD payable, and currently held USD.
- Notional USD must be greater than zero.
- Maturity date must be later than the server's current date.
- Target CNY is optional during the initial no-hedge input step; when provided, it must be greater than zero.
- No strategy, market-data, probability, database, authentication, or frontend integration code is included.
- Existing files under `python/hedging/` and their tests must remain behaviorally unchanged.
- Use test-driven development: fail first, implement the minimum, pass, then commit.

---

## File Structure

```text
python/
├── backend/
│   ├── __init__.py          Python package marker
│   ├── main.py              FastAPI application factory and health endpoint
│   ├── models.py            Exposure request and validation response contracts
│   ├── errors.py            Stable Chinese validation-error conversion
│   └── routes/
│       ├── __init__.py      Routes package marker
│       └── inputs.py        /api/v1/inputs/validate endpoint
├── requirements.txt         Phase 1 runtime and test dependencies
└── tests/
    └── backend/
        ├── test_health.py
        ├── test_models.py
        └── test_input_validation.py
```

Existing `README.md` gains only the commands required to set up and run this backend. Existing `.gitignore` gains the project virtual-environment path.

---

### Task 1: Bootable FastAPI Backend and Health Check

**Files:**
- Modify: `.gitignore`
- Create: `python/requirements.txt`
- Create: `python/backend/__init__.py`
- Create: `python/backend/main.py`
- Create: `python/tests/backend/test_health.py`

**Interfaces:**
- Consumes: Python 3.12 installed as `python3.12`.
- Produces: `backend.main.create_app() -> FastAPI`, module-level `backend.main.app`, and `GET /health` returning service identity and version.

- [ ] **Step 1: Add the isolated Python environment and dependency declarations**

Append this line to `.gitignore`:

```gitignore
/.venv/
```

Create `python/requirements.txt`:

```text
fastapi>=0.116,<1.0
uvicorn[standard]>=0.35,<1.0
httpx>=0.28,<1.0
pytest>=8,<9
```

Create and populate the environment:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r python/requirements.txt
```

Expected: all packages install successfully and `.venv/bin/python --version` prints `Python 3.12.x`.

- [ ] **Step 2: Write the failing health-endpoint test**

Create `python/tests/backend/test_health.py`:

```python
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_endpoint_identifies_backend() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "fx-hedging-backend",
        "version": "0.1.0",
    }
```

- [ ] **Step 3: Run the test and verify the backend does not exist yet**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_health.py -v
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'backend'`.

- [ ] **Step 4: Implement the minimum application**

Create an empty `python/backend/__init__.py`.

Create `python/backend/main.py`:

```python
from fastapi import FastAPI


SERVICE_VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(
        title="企业外汇策略分析 API",
        description="USD/CNY 外汇敞口与策略风险分析后端",
        version=SERVICE_VERSION,
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "fx-hedging-backend",
            "version": SERVICE_VERSION,
        }

    return app


app = create_app()
```

- [ ] **Step 5: Run the focused test and verify it passes**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_health.py -v
```

Expected: `1 passed`.

- [ ] **Step 6: Commit the bootable backend**

```bash
git add .gitignore python/requirements.txt python/backend/__init__.py python/backend/main.py python/tests/backend/test_health.py
git commit -m "feat: add phase one backend health endpoint"
```

---

### Task 2: Exposure Input Contract

**Files:**
- Create: `python/backend/models.py`
- Create: `python/tests/backend/test_models.py`

**Interfaces:**
- Consumes: Pydantic v2 from Task 1 dependencies.
- Produces: `ExposureType`, `AnalysisInput`, and `ValidationResponse` classes used by the API route in Task 3.

- [ ] **Step 1: Write failing model-contract tests**

Create `python/tests/backend/test_models.py`:

```python
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.models import AnalysisInput, ExposureType


def valid_maturity_date() -> date:
    return date.today() + timedelta(days=90)


def test_analysis_input_accepts_usd_receivable_without_target() -> None:
    payload = AnalysisInput(
        exposure_type=ExposureType.USD_RECEIVABLE,
        notional_usd=1_000_000,
        maturity_date=valid_maturity_date(),
    )

    assert payload.currency_pair == "USD/CNY"
    assert payload.notional_usd == 1_000_000
    assert payload.target_cny is None


def test_analysis_input_accepts_positive_target() -> None:
    payload = AnalysisInput(
        exposure_type=ExposureType.USD_PAYABLE,
        notional_usd=500_000,
        maturity_date=valid_maturity_date(),
        target_cny=3_500_000,
    )

    assert payload.target_cny == 3_500_000


@pytest.mark.parametrize("notional_usd", [0, -1])
def test_analysis_input_rejects_non_positive_notional(notional_usd: float) -> None:
    with pytest.raises(ValidationError):
        AnalysisInput(
            exposure_type=ExposureType.USD_HOLDING,
            notional_usd=notional_usd,
            maturity_date=valid_maturity_date(),
        )


def test_analysis_input_rejects_non_usd_cny_pair() -> None:
    with pytest.raises(ValidationError):
        AnalysisInput(
            currency_pair="EUR/CNY",
            exposure_type=ExposureType.USD_RECEIVABLE,
            notional_usd=1_000_000,
            maturity_date=valid_maturity_date(),
        )


def test_analysis_input_rejects_today_as_maturity() -> None:
    with pytest.raises(ValidationError):
        AnalysisInput(
            exposure_type=ExposureType.USD_RECEIVABLE,
            notional_usd=1_000_000,
            maturity_date=date.today(),
        )


@pytest.mark.parametrize("target_cny", [0, -1])
def test_analysis_input_rejects_non_positive_target(target_cny: float) -> None:
    with pytest.raises(ValidationError):
        AnalysisInput(
            exposure_type=ExposureType.USD_PAYABLE,
            notional_usd=1_000_000,
            maturity_date=valid_maturity_date(),
            target_cny=target_cny,
        )
```

- [ ] **Step 2: Run the test and verify the models do not exist yet**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_models.py -v
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'backend.models'`.

- [ ] **Step 3: Implement the input and response models**

Create `python/backend/models.py`:

```python
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
```

- [ ] **Step 4: Run the focused model tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_models.py -v
```

Expected: `8 passed`.

- [ ] **Step 5: Run the existing hedging tests to confirm no regression**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/test_forward.py python/tests/test_option.py python/tests/test_composite.py -v
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit the input contract**

```bash
git add python/backend/models.py python/tests/backend/test_models.py
git commit -m "feat: define phase one exposure input contract"
```

---

### Task 3: Validation Endpoint and Friendly Errors

**Files:**
- Create: `python/backend/errors.py`
- Create: `python/backend/routes/__init__.py`
- Create: `python/backend/routes/inputs.py`
- Modify: `python/backend/main.py`
- Create: `python/tests/backend/test_input_validation.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `AnalysisInput` and `ValidationResponse` from Task 2.
- Produces: `POST /api/v1/inputs/validate`; valid requests return `ValidationResponse`, invalid requests return a stable `validation_error` object with Chinese field messages.

- [ ] **Step 1: Write failing endpoint tests**

Create `python/tests/backend/test_input_validation.py`:

```python
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def future_date() -> str:
    return (date.today() + timedelta(days=90)).isoformat()


def valid_payload() -> dict[str, object]:
    return {
        "currency_pair": "USD/CNY",
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": future_date(),
        "target_cny": 6_800_000,
    }


def test_validate_endpoint_returns_normalized_input() -> None:
    response = client.post("/api/v1/inputs/validate", json=valid_payload())

    assert response.status_code == 200
    assert response.json() == {
        "status": "valid",
        "quote_convention": "CNY per 1 USD",
        "normalized_input": valid_payload(),
    }


def test_validate_endpoint_allows_target_to_be_omitted() -> None:
    payload = valid_payload()
    payload.pop("target_cny")

    response = client.post("/api/v1/inputs/validate", json=payload)

    assert response.status_code == 200
    assert response.json()["normalized_input"]["target_cny"] is None


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        ("currency_pair", "EUR/CNY", "第一版只支持 USD/CNY"),
        ("exposure_type", "investment", "请选择美元应收、美元应付或持有美元"),
        ("notional_usd", 0, "美元金额必须大于 0"),
        ("target_cny", -1, "目标人民币金额必须大于 0"),
    ],
)
def test_validate_endpoint_returns_friendly_field_errors(
    field: str,
    value: object,
    expected_message: str,
) -> None:
    payload = valid_payload()
    payload[field] = value

    response = client.post("/api/v1/inputs/validate", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "输入内容有误",
            "fields": [{"field": field, "message": expected_message}],
        }
    }


def test_validate_endpoint_rejects_non_future_maturity() -> None:
    payload = valid_payload()
    payload["maturity_date"] = date.today().isoformat()

    response = client.post("/api/v1/inputs/validate", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [
        {"field": "maturity_date", "message": "到期日必须晚于今天"}
    ]
```

- [ ] **Step 2: Run the endpoint test and verify the route is missing**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_input_validation.py -v
```

Expected: FAIL because `POST /api/v1/inputs/validate` returns `404`.

- [ ] **Step 3: Implement stable validation-error conversion**

Create `python/backend/errors.py`:

```python
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


FIELD_MESSAGES = {
    "currency_pair": "第一版只支持 USD/CNY",
    "exposure_type": "请选择美元应收、美元应付或持有美元",
    "notional_usd": "美元金额必须大于 0",
    "maturity_date": "到期日必须晚于今天",
    "target_cny": "目标人民币金额必须大于 0",
}


async def validation_exception_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    fields: list[dict[str, str]] = []
    seen: set[str] = set()

    for error in exc.errors():
        location = [str(part) for part in error["loc"] if part != "body"]
        field = location[-1] if location else "request"
        if field in seen:
            continue
        seen.add(field)
        fields.append(
            {
                "field": field,
                "message": FIELD_MESSAGES.get(field, "输入格式不正确"),
            }
        )

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "输入内容有误",
                "fields": fields,
            }
        },
    )
```

- [ ] **Step 4: Implement the validation route**

Create an empty `python/backend/routes/__init__.py`.

Create `python/backend/routes/inputs.py`:

```python
from fastapi import APIRouter

from backend.models import AnalysisInput, ValidationResponse


router = APIRouter(prefix="/api/v1/inputs", tags=["inputs"])


@router.post("/validate", response_model=ValidationResponse)
def validate_analysis_input(payload: AnalysisInput) -> ValidationResponse:
    return ValidationResponse(normalized_input=payload)
```

Replace `python/backend/main.py` with:

```python
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.errors import validation_exception_handler
from backend.routes.inputs import router as inputs_router


SERVICE_VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(
        title="企业外汇策略分析 API",
        description="USD/CNY 外汇敞口与策略风险分析后端",
        version=SERVICE_VERSION,
    )
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.include_router(inputs_router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "fx-hedging-backend",
            "version": SERVICE_VERSION,
        }

    return app


app = create_app()
```

- [ ] **Step 5: Run endpoint and backend tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend -v
```

Expected: all backend tests pass.

- [ ] **Step 6: Document the beginner-friendly setup and manual check**

Append to `README.md`:

````markdown
## 第一阶段 Python 后端

创建独立 Python 3.12 环境并安装依赖：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r python/requirements.txt
```

启动后端：

```bash
.venv/bin/python -m uvicorn backend.main:app --app-dir python --reload
```

启动后可访问：

- 健康检查：`http://127.0.0.1:8000/health`
- 交互式接口说明：`http://127.0.0.1:8000/docs`

运行全部 Python 测试：

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests -v
```
````

Start the backend:

```bash
.venv/bin/python -m uvicorn backend.main:app --app-dir python
```

In a second terminal, run:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/inputs/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "currency_pair": "USD/CNY",
    "exposure_type": "usd_receivable",
    "notional_usd": 1000000,
    "maturity_date": "2030-12-31",
    "target_cny": 6800000
  }'
```

Expected response:

```json
{
  "status": "valid",
  "quote_convention": "CNY per 1 USD",
  "normalized_input": {
    "currency_pair": "USD/CNY",
    "exposure_type": "usd_receivable",
    "notional_usd": 1000000.0,
    "maturity_date": "2030-12-31",
    "target_cny": 6800000.0
  }
}
```

- [ ] **Step 7: Run the full Python regression suite**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests -v
```

Expected: all new backend tests and all existing hedging tests pass.

- [ ] **Step 8: Commit the finished Phase 1 backend**

```bash
git add README.md python/backend/errors.py python/backend/routes/__init__.py python/backend/routes/inputs.py python/backend/main.py python/tests/backend/test_input_validation.py
git commit -m "feat: validate phase one exposure inputs"
```

---

## Phase 1 Acceptance Checklist

- [ ] `.venv/bin/python --version` reports Python 3.12.x.
- [ ] `GET /health` returns status, service name, and version.
- [ ] `POST /api/v1/inputs/validate` accepts USD receivable, payable, and holding inputs.
- [ ] Target CNY may be omitted for the initial no-hedge step and must be positive when supplied.
- [ ] Invalid currency pair, exposure type, amount, target, and maturity return stable Chinese errors.
- [ ] No strategy payoff, market-data, probability, database, or frontend code was added.
- [ ] Existing hedging tests remain green.
- [ ] README commands work from the repository root.
