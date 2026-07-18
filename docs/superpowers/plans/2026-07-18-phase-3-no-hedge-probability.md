# Phase 3 No-Hedge Probability Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic USD/CNY lognormal probability engine that returns an expected no-hedge amount, 50% and 90% amount ranges, and an optional target-achievement probability.

**Architecture:** Add a pure lognormal distribution service that knows only dates, rates, and probabilities. Add a separate no-hedge probability service that combines that distribution with the existing single-scenario `Decimal` amount calculator, while Pydantic models and a thin FastAPI route provide the public contract.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, Python standard-library `math` and `statistics.NormalDist`, `Decimal`, pytest, FastAPI `TestClient`.

## Global Constraints

- Currency pair remains exactly `USD/CNY`, quoted as `CNY per 1 USD`.
- Distribution model is exactly `lognormal` for this phase.
- `assumed_expected_maturity_spot` is the mathematical expected maturity spot and must be finite and greater than 0.
- `assumed_annualized_volatility_pct` is a percentage, so `5.0` means 5%, and must be finite and greater than 0.
- Horizon uses natural days divided by 365 and volatility scales by the square root of the horizon.
- Probability calculations are analytic and deterministic; do not add simulation, SciPy, or NumPy.
- Money calculations must continue through the existing `Decimal` half-up-to-cents path.
- Manual parameters must be labelled as assumptions and never as market forecasts.
- A missing `target_cny` must produce `target_probability: null`.
- The phase does not fetch any external market or institutional data.

---

### Task 1: Define Probability Request and Response Contracts

**Files:**
- Create: `python/tests/backend/test_probability_models.py`
- Modify: `python/backend/models.py`

**Interfaces:**
- Consumes: existing `AnalysisInput`, `ResultKind`, and `ExposureType` from `backend.models`.
- Produces: `NoHedgeProbabilityRequest`, `DistributionMetadata`, `ExpectedResult`, `ProbabilityRange`, `TargetProbability`, and `NoHedgeProbabilityResponse` for Tasks 3 and 4.

- [ ] **Step 1: Write the failing model tests**

Create `python/tests/backend/test_probability_models.py`:

```python
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.models import NoHedgeProbabilityRequest


def future_date() -> date:
    return date.today() + timedelta(days=365)


def test_probability_request_accepts_positive_finite_assumptions() -> None:
    payload = NoHedgeProbabilityRequest(
        exposure_type="usd_receivable",
        notional_usd=1_000_000,
        maturity_date=future_date(),
        target_cny=6_800_000,
        assumed_expected_maturity_spot=6.80,
        assumed_annualized_volatility_pct=5.0,
    )

    assert payload.currency_pair == "USD/CNY"
    assert payload.assumed_expected_maturity_spot == 6.80
    assert payload.assumed_annualized_volatility_pct == 5.0


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_probability_request_rejects_invalid_expected_spot(value: float) -> None:
    with pytest.raises(ValidationError):
        NoHedgeProbabilityRequest(
            exposure_type="usd_receivable",
            notional_usd=1_000_000,
            maturity_date=future_date(),
            assumed_expected_maturity_spot=value,
            assumed_annualized_volatility_pct=5.0,
        )


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_probability_request_rejects_invalid_volatility(value: float) -> None:
    with pytest.raises(ValidationError):
        NoHedgeProbabilityRequest(
            exposure_type="usd_receivable",
            notional_usd=1_000_000,
            maturity_date=future_date(),
            assumed_expected_maturity_spot=6.80,
            assumed_annualized_volatility_pct=value,
        )
```

- [ ] **Step 2: Run the tests and verify that the new model is missing**

Run from the repository root:

```bash
cd python && ../.venv/bin/python -m pytest tests/backend/test_probability_models.py -v
```

Expected: collection fails with an import error for `NoHedgeProbabilityRequest`.

- [ ] **Step 3: Add the probability contract models**

Append these definitions to `python/backend/models.py`:

```python
class NoHedgeProbabilityRequest(AnalysisInput):
    assumed_expected_maturity_spot: Annotated[
        float,
        Field(gt=0, allow_inf_nan=False),
    ]
    assumed_annualized_volatility_pct: Annotated[
        float,
        Field(gt=0, allow_inf_nan=False),
    ]


class DistributionMetadata(BaseModel):
    model_type: Literal["lognormal"] = "lognormal"
    source_type: Literal["assumption"] = "assumption"
    is_market_forecast: Literal[False] = False
    assumed_expected_maturity_spot: float
    assumed_annualized_volatility_pct: float
    horizon_days: int


class ExpectedResult(BaseModel):
    spot: float
    amount_cny: float


class ProbabilityRange(BaseModel):
    probability: float
    lower_spot: float
    upper_spot: float
    lower_amount_cny: float
    upper_amount_cny: float


class TargetProbability(BaseModel):
    target_cny: float
    critical_spot: float
    probability_met: float
    probability_missed: float


class NoHedgeProbabilityResponse(BaseModel):
    status: Literal["calculated"] = "calculated"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    distribution: DistributionMetadata
    result_kind: ResultKind
    expected_result: ExpectedResult
    typical_range_50: ProbabilityRange
    wide_range_90: ProbabilityRange
    target_probability: TargetProbability | None
```

- [ ] **Step 4: Run the model tests and the existing model tests**

Run:

```bash
cd python && ../.venv/bin/python -m pytest tests/backend/test_probability_models.py tests/backend/test_models.py tests/backend/test_no_hedge_models.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit the contract**

```bash
git add python/backend/models.py python/tests/backend/test_probability_models.py
git commit -m "feat: define probability analysis contracts"
```

---

### Task 2: Build the Pure Lognormal Distribution Service

**Files:**
- Create: `python/backend/services/distributions.py`
- Create: `python/tests/backend/test_distributions.py`

**Interfaces:**
- Consumes: `expected_spot: float`, `annualized_volatility_pct: float`, `maturity_date: date`, and an optional `valuation_date: date`.
- Produces: `build_lognormal_distribution(...) -> LognormalDistribution`; the returned object exposes `horizon_days`, `term_volatility`, `mean()`, `quantile(probability)`, and `cdf(spot)`.

- [ ] **Step 1: Write failing distribution tests**

Create `python/tests/backend/test_distributions.py`:

```python
from datetime import date, timedelta

import pytest

from backend.services.distributions import build_lognormal_distribution


VALUATION_DATE = date(2030, 1, 1)


def make_distribution(*, days: int = 365, volatility_pct: float = 5.0):
    return build_lognormal_distribution(
        expected_spot=6.80,
        annualized_volatility_pct=volatility_pct,
        maturity_date=VALUATION_DATE + timedelta(days=days),
        valuation_date=VALUATION_DATE,
    )


def test_distribution_preserves_expected_spot_and_scales_volatility() -> None:
    distribution = make_distribution()

    assert distribution.horizon_days == 365
    assert distribution.term_volatility == pytest.approx(0.05)
    assert distribution.mean() == pytest.approx(6.80)


def test_distribution_returns_ordered_reference_quantiles() -> None:
    distribution = make_distribution()
    quantiles = [distribution.quantile(p) for p in (0.05, 0.25, 0.50, 0.75, 0.95)]

    assert quantiles[0] < quantiles[1] < quantiles[2] < quantiles[3] < quantiles[4]
    assert quantiles[0] == pytest.approx(6.2553051696)
    assert quantiles[-1] == pytest.approx(7.3736681311)


def test_longer_horizon_produces_wider_distribution() -> None:
    one_year = make_distribution(days=365)
    two_years = make_distribution(days=730)

    assert two_years.quantile(0.05) < one_year.quantile(0.05)
    assert two_years.quantile(0.95) > one_year.quantile(0.95)


def test_higher_volatility_produces_wider_distribution() -> None:
    low = make_distribution(volatility_pct=3.0)
    high = make_distribution(volatility_pct=8.0)

    assert high.quantile(0.05) < low.quantile(0.05)
    assert high.quantile(0.95) > low.quantile(0.95)


def test_cdf_is_bounded_and_increases_with_spot() -> None:
    distribution = make_distribution()

    assert distribution.cdf(0) == 0.0
    assert 0 < distribution.cdf(6.50) < distribution.cdf(7.00) < 1


@pytest.mark.parametrize("probability", [0, 1, -0.1, 1.1])
def test_quantile_rejects_non_interior_probability(probability: float) -> None:
    with pytest.raises(ValueError, match="概率必须在 0 和 1 之间"):
        make_distribution().quantile(probability)


def test_distribution_rejects_non_future_maturity() -> None:
    with pytest.raises(ValueError, match="到期日必须晚于估值日"):
        build_lognormal_distribution(
            expected_spot=6.80,
            annualized_volatility_pct=5.0,
            maturity_date=VALUATION_DATE,
            valuation_date=VALUATION_DATE,
        )


def test_distribution_rejects_unrepresentable_parameters() -> None:
    from backend.services.distributions import ProbabilityCalculationError

    with pytest.raises(
        ProbabilityCalculationError,
        match="概率模型无法处理该组参数",
    ):
        make_distribution(volatility_pct=1e308)
```

- [ ] **Step 2: Run the distribution tests and verify the module is missing**

Run:

```bash
cd python && ../.venv/bin/python -m pytest tests/backend/test_distributions.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'backend.services.distributions'`.

- [ ] **Step 3: Implement the pure distribution service**

Create `python/backend/services/distributions.py`:

```python
from dataclasses import dataclass
from datetime import date
from math import exp, isfinite, log, sqrt
from statistics import NormalDist


DAYS_PER_YEAR = 365
STANDARD_NORMAL = NormalDist()


class ProbabilityCalculationError(ValueError):
    pass


def _finite(value: float) -> float:
    if not isfinite(value):
        raise ProbabilityCalculationError("概率模型无法处理该组参数")
    return value


def _positive_finite(value: float) -> float:
    if value <= 0:
        raise ProbabilityCalculationError("概率模型无法处理该组参数")
    return _finite(value)


@dataclass(frozen=True)
class LognormalDistribution:
    expected_spot: float
    horizon_days: int
    term_volatility: float
    log_mean: float

    def mean(self) -> float:
        try:
            return _positive_finite(
                exp(self.log_mean + 0.5 * self.term_volatility**2)
            )
        except OverflowError as exc:
            raise ProbabilityCalculationError("概率模型无法处理该组参数") from exc

    def quantile(self, probability: float) -> float:
        if not 0 < probability < 1:
            raise ValueError("概率必须在 0 和 1 之间")
        z_score = STANDARD_NORMAL.inv_cdf(probability)
        try:
            return _positive_finite(
                exp(self.log_mean + self.term_volatility * z_score)
            )
        except OverflowError as exc:
            raise ProbabilityCalculationError("概率模型无法处理该组参数") from exc

    def cdf(self, spot: float) -> float:
        if spot <= 0:
            return 0.0
        z_score = (log(spot) - self.log_mean) / self.term_volatility
        return min(1.0, max(0.0, STANDARD_NORMAL.cdf(z_score)))


def build_lognormal_distribution(
    *,
    expected_spot: float,
    annualized_volatility_pct: float,
    maturity_date: date,
    valuation_date: date | None = None,
) -> LognormalDistribution:
    effective_valuation_date = valuation_date or date.today()
    horizon_days = (maturity_date - effective_valuation_date).days
    if horizon_days <= 0:
        raise ValueError("到期日必须晚于估值日")

    try:
        annualized_volatility = annualized_volatility_pct / 100
        term_volatility = _finite(
            annualized_volatility * sqrt(horizon_days / DAYS_PER_YEAR)
        )
        log_mean = _finite(log(expected_spot) - 0.5 * term_volatility**2)
    except OverflowError as exc:
        raise ProbabilityCalculationError("概率模型无法处理该组参数") from exc

    return LognormalDistribution(
        expected_spot=expected_spot,
        horizon_days=horizon_days,
        term_volatility=term_volatility,
        log_mean=log_mean,
    )
```

- [ ] **Step 4: Run the distribution tests**

Run:

```bash
cd python && ../.venv/bin/python -m pytest tests/backend/test_distributions.py -v
```

Expected: all distribution tests pass without adding a third-party dependency.

- [ ] **Step 5: Commit the distribution engine**

```bash
git add python/backend/services/distributions.py python/tests/backend/test_distributions.py
git commit -m "feat: calculate lognormal spot probabilities"
```

---

### Task 3: Combine the Distribution with No-Hedge Amount Calculations

**Files:**
- Create: `python/backend/services/no_hedge_probability.py`
- Create: `python/tests/backend/test_no_hedge_probability_service.py`
- Read/reuse: `python/backend/services/no_hedge.py`

**Interfaces:**
- Consumes: `NoHedgeProbabilityRequest`, `build_lognormal_distribution`, and `calculate_no_hedge_scenario`.
- Produces: `calculate_no_hedge_probability(payload, valuation_date=None) -> NoHedgeProbabilityResponse` for Task 4.

- [ ] **Step 1: Write failing probability-service tests**

Create `python/tests/backend/test_no_hedge_probability_service.py`:

```python
from datetime import date, timedelta

import pytest

from backend.models import NoHedgeProbabilityRequest, ResultKind
from backend.services.no_hedge_probability import calculate_no_hedge_probability


VALUATION_DATE = date(2030, 1, 1)


def make_payload(
    *,
    exposure_type: str = "usd_receivable",
    target_cny: float | None = 6_800_000,
) -> NoHedgeProbabilityRequest:
    return NoHedgeProbabilityRequest(
        exposure_type=exposure_type,
        notional_usd=1_000_000,
        maturity_date=VALUATION_DATE + timedelta(days=365),
        target_cny=target_cny,
        assumed_expected_maturity_spot=6.80,
        assumed_annualized_volatility_pct=5.0,
    )


def test_probability_analysis_returns_expected_amount_and_ranges() -> None:
    result = calculate_no_hedge_probability(
        make_payload(),
        valuation_date=VALUATION_DATE,
    )

    assert result.result_kind is ResultKind.CNY_PROCEEDS
    assert result.expected_result.spot == 6.80
    assert result.expected_result.amount_cny == 6_800_000.00
    assert result.typical_range_50.probability == 0.50
    assert result.typical_range_50.lower_spot == pytest.approx(6.5662843507)
    assert result.typical_range_50.upper_spot == pytest.approx(7.0244512598)
    assert result.wide_range_90.probability == 0.90
    assert result.wide_range_90.lower_spot == pytest.approx(6.2553051696)
    assert result.wide_range_90.upper_spot == pytest.approx(7.3736681311)
    assert (
        result.typical_range_50.lower_amount_cny
        < result.typical_range_50.upper_amount_cny
    )
    assert (
        result.wide_range_90.lower_amount_cny
        < result.wide_range_90.upper_amount_cny
    )


def test_receivable_and_payable_use_opposite_probability_tails() -> None:
    receivable = calculate_no_hedge_probability(
        make_payload(exposure_type="usd_receivable"),
        valuation_date=VALUATION_DATE,
    )
    payable = calculate_no_hedge_probability(
        make_payload(exposure_type="usd_payable"),
        valuation_date=VALUATION_DATE,
    )

    assert receivable.target_probability is not None
    assert payable.target_probability is not None
    assert receivable.target_probability.probability_met == pytest.approx(0.4900274818)
    assert payable.target_probability.probability_met == pytest.approx(0.5099725182)
    assert (
        receivable.target_probability.probability_met
        + receivable.target_probability.probability_missed
    ) == pytest.approx(1.0)


@pytest.mark.parametrize("exposure_type", ["usd_receivable", "usd_holding"])
def test_higher_proceeds_target_reduces_probability_met(
    exposure_type: str,
) -> None:
    lower_target = make_payload(exposure_type=exposure_type)
    higher_target = lower_target.model_copy(update={"target_cny": 7_000_000})

    lower_result = calculate_no_hedge_probability(
        lower_target,
        valuation_date=VALUATION_DATE,
    )
    higher_result = calculate_no_hedge_probability(
        higher_target,
        valuation_date=VALUATION_DATE,
    )

    assert lower_result.target_probability is not None
    assert higher_result.target_probability is not None
    assert (
        higher_result.target_probability.probability_met
        < lower_result.target_probability.probability_met
    )


def test_higher_payable_cost_limit_increases_probability_met() -> None:
    lower_target = make_payload(exposure_type="usd_payable")
    higher_target = lower_target.model_copy(update={"target_cny": 7_000_000})

    lower_result = calculate_no_hedge_probability(
        lower_target,
        valuation_date=VALUATION_DATE,
    )
    higher_result = calculate_no_hedge_probability(
        higher_target,
        valuation_date=VALUATION_DATE,
    )

    assert lower_result.target_probability is not None
    assert higher_result.target_probability is not None
    assert (
        higher_result.target_probability.probability_met
        > lower_result.target_probability.probability_met
    )


def test_probability_analysis_omits_target_when_not_supplied() -> None:
    result = calculate_no_hedge_probability(
        make_payload(target_cny=None),
        valuation_date=VALUATION_DATE,
    )

    assert result.target_probability is None


def test_distribution_metadata_marks_inputs_as_assumptions() -> None:
    result = calculate_no_hedge_probability(
        make_payload(),
        valuation_date=VALUATION_DATE,
    )

    assert result.distribution.model_type == "lognormal"
    assert result.distribution.source_type == "assumption"
    assert result.distribution.is_market_forecast is False
    assert result.distribution.horizon_days == 365
```

- [ ] **Step 2: Run the service tests and verify the service is missing**

Run:

```bash
cd python && ../.venv/bin/python -m pytest tests/backend/test_no_hedge_probability_service.py -v
```

Expected: collection fails with an import error for `backend.services.no_hedge_probability`.

- [ ] **Step 3: Implement the probability analysis service**

Create `python/backend/services/no_hedge_probability.py`:

```python
from datetime import date
from decimal import Decimal

from backend.models import (
    DistributionMetadata,
    ExpectedResult,
    ExposureType,
    NoHedgeProbabilityRequest,
    NoHedgeProbabilityResponse,
    NoHedgeScenarioRequest,
    ProbabilityRange,
    ResultKind,
    TargetProbability,
)
from backend.services.distributions import (
    LognormalDistribution,
    build_lognormal_distribution,
)
from backend.services.no_hedge import calculate_no_hedge_scenario


def _amount_at_spot(payload: NoHedgeProbabilityRequest, spot: float) -> float:
    scenario = NoHedgeScenarioRequest(
        currency_pair=payload.currency_pair,
        exposure_type=payload.exposure_type,
        notional_usd=payload.notional_usd,
        maturity_date=payload.maturity_date,
        target_cny=None,
        assumed_maturity_spot=spot,
    )
    return calculate_no_hedge_scenario(scenario).no_hedge_amount_cny


def _probability_range(
    payload: NoHedgeProbabilityRequest,
    distribution: LognormalDistribution,
    *,
    probability: float,
    lower_percentile: float,
    upper_percentile: float,
) -> ProbabilityRange:
    lower_spot = distribution.quantile(lower_percentile)
    upper_spot = distribution.quantile(upper_percentile)
    return ProbabilityRange(
        probability=probability,
        lower_spot=lower_spot,
        upper_spot=upper_spot,
        lower_amount_cny=_amount_at_spot(payload, lower_spot),
        upper_amount_cny=_amount_at_spot(payload, upper_spot),
    )


def _target_probability(
    payload: NoHedgeProbabilityRequest,
    distribution: LognormalDistribution,
) -> TargetProbability | None:
    if payload.target_cny is None:
        return None

    critical_spot_decimal = (
        Decimal(str(payload.target_cny)) / Decimal(str(payload.notional_usd))
    )
    critical_spot = float(critical_spot_decimal)
    probability_below = distribution.cdf(critical_spot)
    if payload.exposure_type is ExposureType.USD_PAYABLE:
        probability_met = probability_below
    else:
        probability_met = 1.0 - probability_below
    probability_met = min(1.0, max(0.0, probability_met))

    return TargetProbability(
        target_cny=payload.target_cny,
        critical_spot=critical_spot,
        probability_met=probability_met,
        probability_missed=1.0 - probability_met,
    )


def calculate_no_hedge_probability(
    payload: NoHedgeProbabilityRequest,
    *,
    valuation_date: date | None = None,
) -> NoHedgeProbabilityResponse:
    distribution = build_lognormal_distribution(
        expected_spot=payload.assumed_expected_maturity_spot,
        annualized_volatility_pct=payload.assumed_annualized_volatility_pct,
        maturity_date=payload.maturity_date,
        valuation_date=valuation_date,
    )
    result_kind = (
        ResultKind.CNY_COST
        if payload.exposure_type is ExposureType.USD_PAYABLE
        else ResultKind.CNY_PROCEEDS
    )

    return NoHedgeProbabilityResponse(
        distribution=DistributionMetadata(
            assumed_expected_maturity_spot=payload.assumed_expected_maturity_spot,
            assumed_annualized_volatility_pct=(
                payload.assumed_annualized_volatility_pct
            ),
            horizon_days=distribution.horizon_days,
        ),
        result_kind=result_kind,
        expected_result=ExpectedResult(
            spot=payload.assumed_expected_maturity_spot,
            amount_cny=_amount_at_spot(
                payload,
                payload.assumed_expected_maturity_spot,
            ),
        ),
        typical_range_50=_probability_range(
            payload,
            distribution,
            probability=0.50,
            lower_percentile=0.25,
            upper_percentile=0.75,
        ),
        wide_range_90=_probability_range(
            payload,
            distribution,
            probability=0.90,
            lower_percentile=0.05,
            upper_percentile=0.95,
        ),
        target_probability=_target_probability(payload, distribution),
    )
```

- [ ] **Step 4: Run the probability service tests and the existing scenario tests**

Run:

```bash
cd python && ../.venv/bin/python -m pytest tests/backend/test_no_hedge_probability_service.py tests/backend/test_no_hedge_service.py -v
```

Expected: all selected tests pass, proving the old amount service still behaves unchanged.

- [ ] **Step 5: Commit the probability analysis service**

```bash
git add python/backend/services/no_hedge_probability.py python/tests/backend/test_no_hedge_probability_service.py
git commit -m "feat: calculate no-hedge probability results"
```

---

### Task 4: Expose the Probability API and Friendly Errors

**Files:**
- Modify: `python/backend/errors.py`
- Modify: `python/backend/main.py`
- Modify: `python/backend/routes/analysis.py`
- Create: `python/tests/backend/test_no_hedge_probability_api.py`

**Interfaces:**
- Consumes: `NoHedgeProbabilityRequest`, `NoHedgeProbabilityResponse`, and `calculate_no_hedge_probability` from Tasks 1 and 3.
- Produces: `POST /api/v1/analysis/no-hedge/probability` with the approved response shape and stable Chinese validation errors.

- [ ] **Step 1: Write failing endpoint tests**

Create `python/tests/backend/test_no_hedge_probability_api.py`:

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
        "maturity_date": (date.today() + timedelta(days=365)).isoformat(),
        "target_cny": 6_800_000,
        "assumed_expected_maturity_spot": 6.80,
        "assumed_annualized_volatility_pct": 5.0,
    }


def test_probability_endpoint_returns_assumption_analysis() -> None:
    response = client.post(
        "/api/v1/analysis/no-hedge/probability",
        json=valid_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "calculated"
    assert body["quote_convention"] == "CNY per 1 USD"
    assert body["distribution"] == {
        "model_type": "lognormal",
        "source_type": "assumption",
        "is_market_forecast": False,
        "assumed_expected_maturity_spot": 6.8,
        "assumed_annualized_volatility_pct": 5.0,
        "horizon_days": 365,
    }
    assert body["expected_result"] == {
        "spot": 6.8,
        "amount_cny": 6_800_000.0,
    }
    assert body["typical_range_50"]["probability"] == 0.5
    assert body["wide_range_90"]["probability"] == 0.9
    assert body["target_probability"]["probability_met"] == pytest.approx(
        0.4900274818
    )
    assert body["target_probability"]["probability_missed"] == pytest.approx(
        0.5099725182
    )


def test_probability_endpoint_allows_target_to_be_omitted() -> None:
    payload = valid_payload()
    payload.pop("target_cny")

    response = client.post(
        "/api/v1/analysis/no-hedge/probability",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["target_probability"] is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "assumed_expected_maturity_spot",
            0,
            "假设预计到期汇率必须是大于 0 的有效数字",
        ),
        (
            "assumed_annualized_volatility_pct",
            0,
            "假设年化波动率必须是大于 0 的有效数字",
        ),
    ],
)
def test_probability_endpoint_returns_friendly_assumption_errors(
    field: str,
    value: float,
    message: str,
) -> None:
    payload = valid_payload()
    payload[field] = value

    response = client.post(
        "/api/v1/analysis/no-hedge/probability",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "输入内容有误",
            "fields": [{"field": field, "message": message}],
        }
    }


def test_probability_endpoint_returns_stable_calculation_error() -> None:
    payload = valid_payload()
    payload["assumed_annualized_volatility_pct"] = 1e308

    response = client.post(
        "/api/v1/analysis/no-hedge/probability",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "probability_calculation_error",
            "message": "当前假设参数超出可计算范围，请降低波动率后重试",
        }
    }
```

- [ ] **Step 2: Run the endpoint tests and verify the route returns 404**

Run:

```bash
cd python && ../.venv/bin/python -m pytest tests/backend/test_no_hedge_probability_api.py -v
```

Expected: endpoint assertions fail because the new route is not registered yet.

- [ ] **Step 3: Add stable validation messages**

Add these entries to `FIELD_MESSAGES` in `python/backend/errors.py`:

```python
    "assumed_expected_maturity_spot": (
        "假设预计到期汇率必须是大于 0 的有效数字"
    ),
    "assumed_annualized_volatility_pct": (
        "假设年化波动率必须是大于 0 的有效数字"
    ),
```

- [ ] **Step 4: Add the stable calculation-error handler**

Add these imports and handler to `python/backend/errors.py`:

```python
from backend.services.distributions import ProbabilityCalculationError


async def probability_calculation_exception_handler(
    _: Request,
    __: ProbabilityCalculationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "probability_calculation_error",
                "message": "当前假设参数超出可计算范围，请降低波动率后重试",
            }
        },
    )
```

Update the imports in `python/backend/main.py`:

```python
from backend.errors import (
    probability_calculation_exception_handler,
    validation_exception_handler,
)
from backend.services.distributions import ProbabilityCalculationError
```

Register the handler inside `create_app()` immediately after the existing validation handler:

```python
    app.add_exception_handler(
        ProbabilityCalculationError,
        probability_calculation_exception_handler,
    )
```

- [ ] **Step 5: Register the probability endpoint**

Update imports in `python/backend/routes/analysis.py` to include:

```python
from backend.models import (
    NoHedgeProbabilityRequest,
    NoHedgeProbabilityResponse,
    NoHedgeScenarioRequest,
    NoHedgeScenarioResponse,
)
from backend.services.no_hedge import calculate_no_hedge_scenario
from backend.services.no_hedge_probability import calculate_no_hedge_probability
```

Append this route below the scenario route:

```python
@router.post(
    "/no-hedge/probability",
    response_model=NoHedgeProbabilityResponse,
)
def no_hedge_probability(
    payload: NoHedgeProbabilityRequest,
) -> NoHedgeProbabilityResponse:
    return calculate_no_hedge_probability(payload)
```

- [ ] **Step 6: Run the endpoint tests**

Run:

```bash
cd python && ../.venv/bin/python -m pytest tests/backend/test_no_hedge_probability_api.py -v
```

Expected: all endpoint tests pass.

- [ ] **Step 7: Run the complete Python regression suite**

Run:

```bash
cd python && ../.venv/bin/python -m pytest -v
```

Expected: every existing and new Python test passes with no failures or errors.

- [ ] **Step 8: Check formatting and the working-tree scope**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` prints nothing; status lists only the intended Phase 3 source and test files.

- [ ] **Step 9: Commit the API integration**

```bash
git add python/backend/errors.py python/backend/main.py python/backend/routes/analysis.py python/tests/backend/test_no_hedge_probability_api.py
git commit -m "feat: expose no-hedge probability analysis"
```

---

## Final Verification Checklist

- [ ] Run `cd python && ../.venv/bin/python -m pytest -v` and confirm the full suite passes.
- [ ] Start the local API with `cd python && ../.venv/bin/python -m uvicorn backend.main:app --reload`.
- [ ] Open `/docs`, manually call `POST /api/v1/analysis/no-hedge/probability`, and confirm expected amount, 50% range, 90% range, and target probabilities are visible.
- [ ] Confirm the response says `source_type: assumption` and `is_market_forecast: false`.
- [ ] Confirm no dependency was added to `python/requirements.txt`.
- [ ] Confirm `git status --short` is clean after the final commit.
