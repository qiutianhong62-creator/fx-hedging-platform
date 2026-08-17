# Phase 11 Probability Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing assumption-driven homepage with a local, real-backend USD/CNY receivable and multi-forward probability dashboard.

**Architecture:** The browser calls the existing FastAPI automatic forward probability endpoint through one typed API module. Python remains the sole owner of financial and probability calculations; React components only validate inputs, control request state, transform response data into view models, and render the approved data-first interface. One backward-compatible backend response field supplies exact interval strategy differences, including over-hedged cases.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, TypeScript 5.9, React 19, Next 16/vinext, native SVG, Node built-in test runner, pnpm.

## Global Constraints

- First version supports only `USD/CNY`, `usd_receivable`, and one shared maturity date.
- Users can enter one or more forward legs with independent USD notionals and forward rates.
- Over-hedging is allowed and must show a warning; never silently cap or rewrite user input.
- Initial analysis sends `target_cny: null`; target analysis reuses the same inputs with one positive target amount.
- The browser calls `http://127.0.0.1:8000` by default through one configurable API module.
- Do not duplicate the Python payoff, distribution, forecast matching, or volatility formulas in TypeScript.
- Data sources, timestamps, weights, cache state, and source fallback status remain visible after a successful analysis.
- Default table shows the 8 highest-probability core intervals, then sorts those selected rows by `lower_spot` ascending.
- Expanded table shows all 20 core intervals plus both open tails.
- Exact-point probability must never be presented as a non-zero probability.
- No new runtime charting or frontend testing dependency; use native SVG, Node tests, the existing build, and browser smoke testing.
- Existing strategy calculation files stay in the repository but are not rendered by the new homepage.
- Because `.openai/hosting.json` exists, implementation must follow the Sites building workflow while preserving the user-selected local-first behavior.
- All UI copy is Chinese and must avoid recommendation, guarantee, or certain-return language.

## Execution Preflight

Run from the Phase 11 worktree root before Task 1:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r python/requirements.txt
pnpm install --frozen-lockfile
```

Expected: Python dependencies install successfully and `node_modules` is available without changing `pnpm-lock.yaml`.

---

### Task 1: Return exact per-interval strategy differences from Python

**Files:**
- Modify: `python/backend/forward_strategy/schemas.py`
- Modify: `python/backend/forward_strategy/probability.py`
- Modify: `python/tests/backend/test_forward_strategy_probability.py`
- Modify: `python/tests/backend/test_automatic_forward_strategy_probability_api.py`

**Interfaces:**
- Consumes: `scenario_amounts_at_spot(payload, spot) -> ScenarioAmounts`
- Produces: `ForwardProbabilityProfileInterval.strategy_minus_no_hedge: ProfileAmountRange`
- Invariant: each difference endpoint is calculated at one spot endpoint before the two values are sorted.

- [ ] **Step 1: Write failing service tests for partial and over-hedged interval differences**

Append to `python/tests/backend/test_forward_strategy_probability.py`:

```python
def assert_interval_difference_matches_spot_endpoints(
    payload: ForwardStrategyProbabilityRequest,
) -> None:
    result = calculate(payload)
    for interval in result.probability_profile.intervals:
        lower = scenario_amounts_at_spot(payload, interval.lower_spot)
        upper = scenario_amounts_at_spot(payload, interval.upper_spot)
        expected = sorted(
            [
                lower.strategy_amount_cny - lower.no_hedge_amount_cny,
                upper.strategy_amount_cny - upper.no_hedge_amount_cny,
            ]
        )
        assert interval.strategy_minus_no_hedge.minimum_amount_cny == (
            pytest.approx(expected[0], abs=0.01)
        )
        assert interval.strategy_minus_no_hedge.maximum_amount_cny == (
            pytest.approx(expected[1], abs=0.01)
        )


def test_partial_hedge_profile_returns_exact_difference_ranges() -> None:
    assert_interval_difference_matches_spot_endpoints(request())


def test_overhedged_profile_returns_exact_difference_ranges() -> None:
    assert_interval_difference_matches_spot_endpoints(
        request(
            legs=[
                {"notional_usd": 1_500_000, "forward_rate": 6.80}
            ]
        )
    )
```

- [ ] **Step 2: Add a failing API contract assertion**

Extend the existing interval-key assertion in `python/tests/backend/test_automatic_forward_strategy_probability_api.py`:

```python
assert set(profile["intervals"][0]) >= {
    "lower_spot",
    "upper_spot",
    "interval_probability",
    "probability_below_upper",
    "probability_above_upper",
    "no_hedge",
    "forward_strategy",
    "strategy_minus_no_hedge",
}
assert set(profile["intervals"][0]["strategy_minus_no_hedge"]) == {
    "minimum_amount_cny",
    "maximum_amount_cny",
}
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
cd python
../.venv/bin/python -m pytest \
  tests/backend/test_forward_strategy_probability.py \
  tests/backend/test_automatic_forward_strategy_probability_api.py -q
```

Expected: failures report that `ForwardProbabilityProfileInterval` has no `strategy_minus_no_hedge` field.

- [ ] **Step 4: Add the response field and one endpoint-correlated helper**

Add to `ForwardProbabilityProfileInterval` in `python/backend/forward_strategy/schemas.py`:

```python
class ForwardProbabilityProfileInterval(BaseModel):
    lower_spot: float
    upper_spot: float
    interval_probability: float
    probability_below_upper: float
    probability_above_upper: float
    no_hedge: ProfileAmountRange
    forward_strategy: ProfileAmountRange
    strategy_minus_no_hedge: ProfileAmountRange
```

Add to `python/backend/forward_strategy/probability.py` immediately after `_profile_amount_range`:

```python
def _profile_difference_range(
    bucket: SpotProbabilityBucket,
    amounts_by_spot: dict[float, ScenarioAmounts],
) -> ProfileAmountRange:
    lower = amounts_by_spot[bucket.lower_spot]
    upper = amounts_by_spot[bucket.upper_spot]
    values = [
        cny_amount(
            Decimal(str(lower.strategy_amount_cny))
            - Decimal(str(lower.no_hedge_amount_cny))
        ),
        cny_amount(
            Decimal(str(upper.strategy_amount_cny))
            - Decimal(str(upper.no_hedge_amount_cny))
        ),
    ]
    return ProfileAmountRange(
        minimum_amount_cny=float(min(values)),
        maximum_amount_cny=float(max(values)),
    )
```

Pass it while constructing each interval:

```python
strategy_minus_no_hedge=_profile_difference_range(
    interval,
    amounts_by_spot,
),
```

- [ ] **Step 5: Run focused and complete backend tests**

Run:

```bash
cd python
../.venv/bin/python -m pytest \
  tests/backend/test_forward_strategy_probability.py \
  tests/backend/test_automatic_forward_strategy_probability_api.py -q
../.venv/bin/python -m pytest tests -q
```

Expected: focused tests pass; complete backend suite passes with no new warnings.

- [ ] **Step 6: Commit Task 1**

```bash
git add \
  python/backend/forward_strategy/schemas.py \
  python/backend/forward_strategy/probability.py \
  python/tests/backend/test_forward_strategy_probability.py \
  python/tests/backend/test_automatic_forward_strategy_probability_api.py
git commit -m "feat: expose interval strategy differences"
```

---

### Task 2: Permit only approved local frontend origins

**Files:**
- Modify: `python/backend/main.py`
- Create: `python/tests/backend/test_cors.py`

**Interfaces:**
- Consumes: browser preflight requests from local vinext/Vite development servers.
- Produces: CORS headers for ports 3000 and 5173 on `localhost` and `127.0.0.1` only.

- [ ] **Step 1: Write failing CORS tests**

Create `python/tests/backend/test_cors.py`:

```python
import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
)
def test_local_frontend_origin_can_preflight(origin: str) -> None:
    response = client.options(
        "/api/v1/analysis/forward-strategy/automatic-probability",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_unapproved_origin_does_not_receive_allow_origin_header() -> None:
    response = client.options(
        "/api/v1/analysis/forward-strategy/automatic-probability",
        headers={
            "Origin": "https://unapproved.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
cd python
../.venv/bin/python -m pytest tests/backend/test_cors.py -q
```

Expected: approved-origin tests fail because the app has no CORS middleware.

- [ ] **Step 3: Add narrowly scoped CORS middleware**

Modify `python/backend/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware


LOCAL_FRONTEND_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
```

Inside `create_app`, after constructing `FastAPI` and before including routers:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
```

- [ ] **Step 4: Verify CORS and backend regression tests**

Run:

```bash
cd python
../.venv/bin/python -m pytest tests/backend/test_cors.py -q
../.venv/bin/python -m pytest tests -q
```

Expected: all tests pass; the unapproved origin still lacks `access-control-allow-origin`.

- [ ] **Step 5: Commit Task 2**

```bash
git add python/backend/main.py python/tests/backend/test_cors.py
git commit -m "feat: allow local probability dashboard requests"
```

---

### Task 3: Add the typed frontend API boundary

**Files:**
- Create: `lib/api/forwardProbability.ts`
- Create: `tests/forward-probability-api.test.ts`
- Modify: `package.json`
- Modify: `tsconfig.json`

**Interfaces:**
- Produces: `ForwardProbabilityRequest`, `AutomaticForwardProbabilityResponse`, `ForwardProbabilityApiError`, and `requestForwardProbability`.
- Consumes: FastAPI JSON success and `{ error: { code, message, fields? } }` failures.

- [ ] **Step 1: Add the Node unit-test script**

Add to `package.json` scripts without changing existing build commands:

```json
"test:unit": "node --experimental-strip-types --test tests/*.test.ts",
"test": "pnpm run test:unit && pnpm run build && node --test tests/rendered-html.test.mjs"
```

Because Node ESM tests need explicit `.ts` extensions and this project uses `noEmit`, add to `compilerOptions` in `tsconfig.json`:

```json
"allowImportingTsExtensions": true
```

- [ ] **Step 2: Write failing API tests**

Create `tests/forward-probability-api.test.ts` with a compact valid response fixture and these tests:

```typescript
import assert from "node:assert/strict";
import test from "node:test";

import {
  ForwardProbabilityApiError,
  requestForwardProbability,
  type ForwardProbabilityRequest,
} from "../lib/api/forwardProbability.ts";

const request: ForwardProbabilityRequest = {
  currency_pair: "USD/CNY",
  exposure_type: "usd_receivable",
  notional_usd: 1_000_000,
  maturity_date: "2026-12-31",
  target_cny: null,
  forward_legs: [
    { notional_usd: 300_000, forward_rate: 6.8 },
    { notional_usd: 200_000, forward_rate: 6.75 },
  ],
};

test("posts the exact automatic probability request", async () => {
  let capturedUrl = "";
  let capturedInit: RequestInit | undefined;
  const fetcher: typeof fetch = async (input, init) => {
    capturedUrl = String(input);
    capturedInit = init;
    return new Response(JSON.stringify({ status: "calculated" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  await requestForwardProbability(request, {
    baseUrl: "http://127.0.0.1:8000",
    fetcher,
  });

  assert.equal(
    capturedUrl,
    "http://127.0.0.1:8000/api/v1/analysis/forward-strategy/automatic-probability",
  );
  assert.equal(capturedInit?.method, "POST");
  assert.deepEqual(JSON.parse(String(capturedInit?.body)), request);
});

test("normalizes FastAPI field errors", async () => {
  const fetcher: typeof fetch = async () => new Response(
    JSON.stringify({
      error: {
        code: "validation_error",
        message: "输入内容有误",
        fields: [{ field: "forward_rate", message: "远期汇率必须大于 0" }],
      },
    }),
    { status: 422, headers: { "content-type": "application/json" } },
  );

  await assert.rejects(
    requestForwardProbability(request, { fetcher }),
    (error: unknown) => {
      assert.ok(error instanceof ForwardProbabilityApiError);
      assert.equal(error.code, "validation_error");
      assert.equal(error.fields[0]?.field, "forward_rate");
      return true;
    },
  );
});

test("maps a rejected fetch to connection_error", async () => {
  const fetcher: typeof fetch = async () => {
    throw new TypeError("fetch failed");
  };

  await assert.rejects(
    requestForwardProbability(request, { fetcher }),
    (error: unknown) => {
      assert.ok(error instanceof ForwardProbabilityApiError);
      assert.equal(error.code, "connection_error");
      assert.match(error.message, /Python 服务未连接/);
      return true;
    },
  );
});
```

- [ ] **Step 3: Run the unit test and verify RED**

Run:

```bash
pnpm run test:unit
```

Expected: module-not-found failure for `lib/api/forwardProbability.ts`.

- [ ] **Step 4: Implement complete request/response types and error normalization**

Create `lib/api/forwardProbability.ts`. Define exact TypeScript shapes for all response fields used by the UI, including:

```typescript
export type AmountRange = {
  minimum_amount_cny: number;
  maximum_amount_cny: number;
};

export type ForwardProbabilityInterval = {
  lower_spot: number;
  upper_spot: number;
  interval_probability: number;
  probability_below_upper: number;
  probability_above_upper: number;
  no_hedge: AmountRange;
  forward_strategy: AmountRange;
  strategy_minus_no_hedge: AmountRange;
};

export type ForwardProbabilityRequest = {
  currency_pair: "USD/CNY";
  exposure_type: "usd_receivable";
  notional_usd: number;
  maturity_date: string;
  target_cny: number | null;
  forward_legs: Array<{ notional_usd: number; forward_rate: number }>;
};
```

Define the remaining response contract exactly as follows, reusing `AmountRange` and `ForwardProbabilityInterval` above:

```typescript
export type ProbabilityRange = AmountRange & { probability: number };
export type TargetProbability = {
  target_cny: number;
  critical_spot: number | null;
  probability_met: number;
  probability_missed: number;
};
export type Coverage = {
  total_forward_notional_usd: number;
  coverage_ratio: number;
  unhedged_notional_usd: number;
  overhedged_notional_usd: number;
  status: "partial_hedge" | "full_hedge" | "over_hedged";
  warnings: Array<{ code: "over_hedged"; message: string }>;
};
export type StrategyResult = {
  expected_amount_cny: number;
  typical_range_50: ProbabilityRange;
  wide_range_90: ProbabilityRange;
  target_probability: TargetProbability | null;
};
export type ForecastSource = {
  institution: "ING" | "MUFG";
  matched_maturity_spot: number;
  weight: 0.5 | 1;
  matching: {
    method: "direct" | "interpolated";
    is_system_estimate: boolean;
    day_weight: number | null;
    anchors: Array<{ source: "ING" | "MUFG" | "FRED"; date: string; spot: number }>;
  };
  source_updated_date: string;
  source_url: string;
  forecast_points: Array<{ date: string; spot: number }>;
  cache_status: "live_fetch" | "daily_cache" | "stale_fallback";
  fetched_at_utc: string;
  cache_age_hours: number;
  is_stale: boolean;
};
export type AutomaticForwardProbabilityResponse = {
  status: "calculated";
  quote_convention: "CNY per 1 USD";
  result_kind: "cny_proceeds";
  distribution: {
    model_type: "lognormal";
    source_type: "market_data";
    is_market_forecast: true;
    assumed_expected_maturity_spot: number;
    assumed_annualized_volatility_pct: number;
    horizon_days: number;
    typical_spot_range_50: { probability: number; lower_spot: number; upper_spot: number };
    wide_spot_range_90: { probability: number; lower_spot: number; upper_spot: number };
  };
  no_hedge: StrategyResult;
  forward_strategy: StrategyResult & { coverage: Coverage };
  comparison: {
    break_even_spot: number;
    probability_strategy_better: number;
    probability_no_hedge_better: number;
    wide_range_90_width: {
      no_hedge_width_cny: number;
      strategy_width_cny: number;
      strategy_minus_no_hedge_cny: number;
      change: "reduced" | "unchanged" | "increased";
    };
  };
  probability_profile: {
    core_lower_spot: number;
    core_upper_spot: number;
    core_probability: number;
    bucket_count: number;
    intervals: ForwardProbabilityInterval[];
    lower_tail: {
      direction: "below";
      boundary_spot: number;
      probability: number;
      no_hedge_amount_cny: number;
      forward_strategy_amount_cny: number;
    };
    upper_tail: {
      direction: "above";
      boundary_spot: number;
      probability: number;
      no_hedge_amount_cny: number;
      forward_strategy_amount_cny: number;
    };
  };
  data_sources: {
    forecast: {
      status: "available";
      currency_pair: "USD/CNY";
      quote_convention: "CNY per 1 USD";
      valuation_date: string;
      maturity_date: string;
      expected_maturity_spot: number;
      source_count: 1 | 2;
      aggregation_status: "equal_weight_consensus" | "single_source_fallback";
      is_consensus_forecast: boolean;
      sources: ForecastSource[];
      unavailable_sources: Array<{
        institution: "ING" | "MUFG";
        reason_code: "fetch_failed" | "source_invalid" | "source_stale" | "horizon_insufficient";
      }>;
      limitations: string[];
    };
    market_history: {
      status: "available";
      currency_pair: "USD/CNY";
      quote_convention: "CNY per 1 USD";
      market_reference: { spot: number; observation_date: string; is_live_quote: false };
      historical_volatility: {
        annualized_volatility_pct: number;
        method: "daily_log_returns_sample_stddev";
        trading_days_per_year: 252;
        window: "1y";
        window_start: string;
        window_end: string;
        observation_count: number;
        return_count: number;
      };
      source: {
        provider: "FRED";
        series_id: "DEXCHUS";
        fetched_at_utc: string;
        cache_status: "live_fetch" | "daily_cache" | "stale_fallback";
        cache_age_hours: number;
        data_age_days: number;
        is_stale: boolean;
      };
    };
  };
  limitations: string[];
};
```

Implement the request boundary:

```typescript
export class ForwardProbabilityApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly fields: Array<{ field: string; message: string }> = [],
    public readonly status: number | null = null,
  ) {
    super(message);
    this.name = "ForwardProbabilityApiError";
  }
}

type RequestOptions = {
  baseUrl?: string;
  fetcher?: typeof fetch;
};

const defaultBaseUrl =
  process.env.NEXT_PUBLIC_FX_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function requestForwardProbability(
  payload: ForwardProbabilityRequest,
  options: RequestOptions = {},
): Promise<AutomaticForwardProbabilityResponse> {
  const fetcher = options.fetcher ?? fetch;
  let response: Response;
  try {
    response = await fetcher(
      `${options.baseUrl ?? defaultBaseUrl}/api/v1/analysis/forward-strategy/automatic-probability`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
  } catch {
    throw new ForwardProbabilityApiError(
      "connection_error",
      "Python 服务未连接，请启动后端后重试。",
    );
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ForwardProbabilityApiError(
      error?.code ?? "analysis_error",
      error?.message ?? "分析失败，请稍后重试。",
      error?.fields ?? [],
      response.status,
    );
  }
  return body as AutomaticForwardProbabilityResponse;
}
```

- [ ] **Step 5: Run API tests and type/build check**

Run:

```bash
pnpm run test:unit
pnpm run build
```

Expected: three API tests pass and the existing site builds.

- [ ] **Step 6: Commit Task 3**

```bash
git add package.json tsconfig.json lib/api/forwardProbability.ts tests/forward-probability-api.test.ts
git commit -m "feat: add typed forward probability client"
```

---

### Task 4: Add deterministic input and probability view models

**Files:**
- Create: `lib/analysis/probabilityDashboard.ts`
- Create: `tests/probability-dashboard.test.ts`

**Interfaces:**
- Produces: `createInitialDraft`, `validateDraft`, `buildRequest`, `coverageSummary`, `selectCoreIntervals`, `allProbabilityRows`, and display formatters.
- Consumes: types from `lib/api/forwardProbability.ts`.

- [ ] **Step 1: Write failing view-model tests**

Create `tests/probability-dashboard.test.ts` covering these exact behaviors:

```typescript
import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRequest,
  coverageSummary,
  selectCoreIntervals,
  validateDraft,
} from "../lib/analysis/probabilityDashboard.ts";

const draft = {
  notionalUsd: 1_000_000,
  maturityDate: "2099-12-31",
  targetCny: null,
  legs: [
    { id: "forward-1", notionalUsd: 300_000, forwardRate: 6.8 },
    { id: "forward-2", notionalUsd: 200_000, forwardRate: 6.75 },
  ],
};

test("builds the fixed USD receivable request without a target", () => {
  assert.deepEqual(buildRequest(draft, null), {
    currency_pair: "USD/CNY",
    exposure_type: "usd_receivable",
    notional_usd: 1_000_000,
    maturity_date: "2099-12-31",
    target_cny: null,
    forward_legs: [
      { notional_usd: 300_000, forward_rate: 6.8 },
      { notional_usd: 200_000, forward_rate: 6.75 },
    ],
  });
});

test("coverage allows and reports over-hedging", () => {
  const summary = coverageSummary({
    ...draft,
    legs: [{ id: "forward-1", notionalUsd: 1_200_000, forwardRate: 6.8 }],
  });
  assert.equal(summary.status, "over_hedged");
  assert.equal(summary.overhedgedUsd, 200_000);
  assert.equal(summary.coverageRatio, 1.2);
});

test("validation rejects invalid fields but not over-hedging", () => {
  assert.deepEqual(validateDraft({ ...draft, notionalUsd: 0 }), {
    notionalUsd: "美元应收金额必须大于 0",
  });
  assert.deepEqual(validateDraft({
    ...draft,
    legs: [{ id: "forward-1", notionalUsd: 1_200_000, forwardRate: 6.8 }],
  }), {});
});

test("selects eight highest probabilities then restores spot order", () => {
  const intervals = Array.from({ length: 20 }, (_, index) => ({
    lower_spot: 6.4 + index * 0.01,
    upper_spot: 6.41 + index * 0.01,
    interval_probability: index / 100,
    probability_below_upper: index / 20,
    probability_above_upper: 1 - index / 20,
    no_hedge: { minimum_amount_cny: 1, maximum_amount_cny: 2 },
    forward_strategy: { minimum_amount_cny: 2, maximum_amount_cny: 3 },
    strategy_minus_no_hedge: { minimum_amount_cny: 1, maximum_amount_cny: 1 },
  }));
  const selected = selectCoreIntervals(intervals, 8);
  assert.deepEqual(
    selected.map((item) => item.lower_spot),
    intervals.slice(12).map((item) => item.lower_spot),
  );
});
```

Add these exact edge tests to the same file:

```typescript
test("validation identifies missing date and invalid leg values", () => {
  assert.deepEqual(validateDraft({
    ...draft,
    maturityDate: "",
    legs: [{ id: "forward-1", notionalUsd: 0, forwardRate: 0 }],
  }), {
    maturityDate: "请选择晚于今天的分析到期日",
    legs: "每笔远期的金额和报价都必须大于 0",
  });
});

test("probability ties keep original bucket order", () => {
  const tied = intervalsFixture.map((item) => ({
    ...item,
    interval_probability: 0.05,
  }));
  assert.deepEqual(
    selectCoreIntervals(tied, 8).map((item) => item.lower_spot),
    tied.slice(0, 8).map((item) => item.lower_spot),
  );
});

test("tiny nonzero probability is not formatted as zero", () => {
  assert.equal(formatProbability(0.0002), "<0.1%");
});
```

Define `intervalsFixture` once at the top of the test file using the 20-interval factory from the preceding selection test, then reuse it in both selection tests.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pnpm run test:unit
```

Expected: module-not-found failure for `lib/analysis/probabilityDashboard.ts`.

- [ ] **Step 3: Implement the pure view-model module**

Create `lib/analysis/probabilityDashboard.ts` with no React imports. Use these public types and signatures:

```typescript
export type ForwardLegDraft = {
  id: string;
  notionalUsd: number;
  forwardRate: number;
};

export type AnalysisDraft = {
  notionalUsd: number;
  maturityDate: string;
  targetCny: number | null;
  legs: ForwardLegDraft[];
};

export type DraftErrors = Partial<Record<
  "notionalUsd" | "maturityDate" | "legs" | "targetCny",
  string
>>;

export function coverageSummary(draft: AnalysisDraft) {
  const totalForwardUsd = draft.legs.reduce(
    (total, leg) => total + leg.notionalUsd,
    0,
  );
  const coverageRatio = draft.notionalUsd > 0
    ? totalForwardUsd / draft.notionalUsd
    : 0;
  const overhedgedUsd = Math.max(0, totalForwardUsd - draft.notionalUsd);
  return {
    totalForwardUsd,
    coverageRatio,
    unhedgedUsd: Math.max(0, draft.notionalUsd - totalForwardUsd),
    overhedgedUsd,
    status: overhedgedUsd > 0
      ? "over_hedged" as const
      : totalForwardUsd === draft.notionalUsd
        ? "full_hedge" as const
        : "partial_hedge" as const,
  };
}
```

Implement the public functions with these exact rules:

```typescript
export function validateDraft(draft: AnalysisDraft): DraftErrors {
  const errors: DraftErrors = {};
  if (!Number.isFinite(draft.notionalUsd) || draft.notionalUsd <= 0) {
    errors.notionalUsd = "美元应收金额必须大于 0";
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const maturity = draft.maturityDate
    ? new Date(`${draft.maturityDate}T00:00:00`)
    : null;
  if (!maturity || Number.isNaN(maturity.valueOf()) || maturity <= today) {
    errors.maturityDate = "请选择晚于今天的分析到期日";
  }
  if (draft.legs.length === 0) {
    errors.legs = "请至少保留一笔远期交易";
  } else if (draft.legs.some((leg) =>
    !Number.isFinite(leg.notionalUsd)
    || leg.notionalUsd <= 0
    || !Number.isFinite(leg.forwardRate)
    || leg.forwardRate <= 0
  )) {
    errors.legs = "每笔远期的金额和报价都必须大于 0";
  }
  if (draft.targetCny !== null
    && (!Number.isFinite(draft.targetCny) || draft.targetCny <= 0)) {
    errors.targetCny = "目标人民币金额必须大于 0";
  }
  return errors;
}

export function buildRequest(
  draft: AnalysisDraft,
  targetCny: number | null,
): ForwardProbabilityRequest {
  return {
    currency_pair: "USD/CNY",
    exposure_type: "usd_receivable",
    notional_usd: draft.notionalUsd,
    maturity_date: draft.maturityDate,
    target_cny: targetCny,
    forward_legs: draft.legs.map((leg) => ({
      notional_usd: leg.notionalUsd,
      forward_rate: leg.forwardRate,
    })),
  };
}

export function selectCoreIntervals(
  intervals: ForwardProbabilityInterval[],
  count = 8,
): ForwardProbabilityInterval[] {
  return intervals
    .map((interval, index) => ({ interval, index }))
    .sort((left, right) =>
      right.interval.interval_probability - left.interval.interval_probability
      || left.index - right.index
    )
    .slice(0, count)
    .map(({ interval }) => interval)
    .sort((left, right) => left.lower_spot - right.lower_spot);
}

export function formatProbability(value: number): string {
  if (value > 0 && value < 0.001) return "<0.1%";
  return `${(value * 100).toFixed(1)}%`;
}
```

Also export `createInitialDraft`, `formatCnyWan`, `formatFullCny`, `formatUsd`, `formatSpot`, `mostLikelyInterval`, and `allProbabilityRows` with the display rules from the design. `buildRequest` must not accept an exposure type argument.

- [ ] **Step 4: Run unit tests and build**

Run:

```bash
pnpm run test:unit
pnpm run build
```

Expected: all TypeScript unit tests and the existing build pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add lib/analysis/probabilityDashboard.ts tests/probability-dashboard.test.ts
git commit -m "feat: add probability dashboard view models"
```

---

### Task 5: Replace the homepage with the live input workflow

**Files:**
- Create: `components/probability-dashboard/ForwardLegEditor.tsx`
- Create: `components/probability-dashboard/AnalysisInputPanel.tsx`
- Create: `components/probability-dashboard/ProbabilityDashboard.tsx`
- Modify: `app/page.tsx`
- Modify: `app/globals.css`
- Modify: `tests/rendered-html.test.mjs`

**Interfaces:**
- Consumes: Task 3 API client and Task 4 draft helpers.
- Produces: initial form, multi-leg editing, initial request lifecycle, stale-result state, and connection/validation messages.

- [ ] **Step 1: Replace old rendered-copy expectations with failing new-homepage expectations**

In `tests/rendered-html.test.mjs`, replace the first test body assertions after title with:

```javascript
assert.match(html, /USD\/CNY · 美元应收 · 同一到期日/);
assert.match(html, /美元应收金额/);
assert.match(html, /分析到期日/);
assert.match(html, /远期结汇交易/);
assert.match(html, /添加一笔远期/);
assert.match(html, /远期总金额/);
assert.match(html, /开始概率分析/);
assert.match(html, /数据来自 ING、MUFG 与 FRED/);
assert.doesNotMatch(html, /观察的到期即期汇率/);
assert.doesNotMatch(html, /自由交易搭建器/);
```

- [ ] **Step 2: Run rendered test and verify RED**

Run:

```bash
pnpm run build
node --test tests/rendered-html.test.mjs
```

Expected: failures show old homepage text and missing new probability copy.

- [ ] **Step 3: Build focused input components**

`ForwardLegEditor.tsx` receives one leg, its one-based index, change callback, delete callback, and `canDelete`. It renders labeled numeric inputs for USD amount and CNY-per-USD rate, plus a delete button disabled when only one leg remains.

`AnalysisInputPanel.tsx` receives the entire draft, errors, loading state, coverage summary, and callbacks. It renders the fixed scope label, exposure and date fields, all forward legs, add button, coverage summary, over-hedge warning, stale-results notice, and submit button.

Use stable leg IDs generated with a `useRef` counter in the parent. Do not use array indexes as React keys.

Use these component contracts:

```tsx
type ForwardLegEditorProps = {
  leg: ForwardLegDraft;
  index: number;
  canDelete: boolean;
  onChange: (id: string, patch: Partial<ForwardLegDraft>) => void;
  onDelete: (id: string) => void;
};

type AnalysisInputPanelProps = {
  draft: AnalysisDraft;
  errors: DraftErrors;
  loading: boolean;
  stale: boolean;
  coverage: ReturnType<typeof coverageSummary>;
  onDraftChange: (patch: Partial<AnalysisDraft>) => void;
  onLegChange: (id: string, patch: Partial<ForwardLegDraft>) => void;
  onAddLeg: () => void;
  onDeleteLeg: (id: string) => void;
  onSubmit: () => void;
};
```

Every numeric input converts an empty string to `Number.NaN`, so incomplete typing stays visible and is caught by `validateDraft`. The form submit handler calls `event.preventDefault()` and delegates to `onSubmit`.

- [ ] **Step 4: Implement request state in `ProbabilityDashboard.tsx`**

Use this explicit state shape:

```typescript
type DashboardStatus =
  | "idle"
  | "loading_initial"
  | "success"
  | "loading_target"
  | "validation_error"
  | "connection_error"
  | "analysis_error";

const [draft, setDraft] = useState<AnalysisDraft>(createInitialDraft());
const [status, setStatus] = useState<DashboardStatus>("idle");
const [errors, setErrors] = useState<DraftErrors>({});
const [response, setResponse] = useState<AutomaticForwardProbabilityResponse | null>(null);
const [errorMessage, setErrorMessage] = useState<string | null>(null);
const [isStale, setIsStale] = useState(false);
```

On any base-input edit after a successful response, preserve the response and set `isStale` to true. On initial submit, validate, send `buildRequest(draft, null)`, map `ForwardProbabilityApiError.code` into page status, and only replace the response after success.

Use this request function in the parent:

```tsx
const runInitialAnalysis = async () => {
  const nextErrors = validateDraft({ ...draft, targetCny: null });
  setErrors(nextErrors);
  if (Object.keys(nextErrors).length > 0) {
    setStatus("validation_error");
    return;
  }
  setStatus("loading_initial");
  setErrorMessage(null);
  try {
    const nextResponse = await requestForwardProbability(
      buildRequest(draft, null),
    );
    setResponse(nextResponse);
    setStatus("success");
    setIsStale(false);
  } catch (error) {
    const normalized = error instanceof ForwardProbabilityApiError
      ? error
      : new ForwardProbabilityApiError(
          "analysis_error",
          "分析失败，请稍后重试。",
        );
    setErrorMessage(normalized.message);
    setStatus(
      normalized.code === "connection_error"
        ? "connection_error"
        : normalized.code === "validation_error"
          ? "validation_error"
          : "analysis_error",
    );
  }
};
```

- [ ] **Step 5: Make `app/page.tsx` a thin route**

Replace its content with:

```tsx
import { ProbabilityDashboard } from "../components/probability-dashboard/ProbabilityDashboard";

export default function Home() {
  return <ProbabilityDashboard />;
}
```

- [ ] **Step 6: Add input-first responsive styles**

Replace obsolete homepage-specific CSS with new scoped classes for the dashboard shell, header, input card, leg cards, coverage strip, buttons, inline errors, status banners, and mobile stacking. Preserve the existing color variables where they meet contrast requirements. Ensure all controls have visible `:focus-visible` states.

Minimum responsive rules:

```css
.probability-dashboard { width: min(1280px, calc(100% - 40px)); margin: 0 auto; }
.analysis-input-grid { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 24px; }
.forward-leg-row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: end; }
.field-error, .overhedge-warning, .status-error { color: #9b361f; }
button:focus-visible, input:focus-visible, a:focus-visible { outline: 3px solid rgba(8,127,115,.3); outline-offset: 2px; }
@media (max-width: 800px) {
  .probability-dashboard { width: min(100% - 24px, 680px); }
  .analysis-input-grid, .forward-leg-row { grid-template-columns: 1fr; }
}
```

- [ ] **Step 7: Run unit, build, and rendered tests**

Run:

```bash
pnpm run test:unit
pnpm run build
node --test tests/rendered-html.test.mjs
```

Expected: unit tests pass; build succeeds; rendered HTML includes the new form and excludes the old assumption inputs.

- [ ] **Step 8: Commit Task 5**

```bash
git add \
  components/probability-dashboard/ForwardLegEditor.tsx \
  components/probability-dashboard/AnalysisInputPanel.tsx \
  components/probability-dashboard/ProbabilityDashboard.tsx \
  app/page.tsx app/globals.css tests/rendered-html.test.mjs
git commit -m "feat: replace homepage with probability inputs"
```

---

### Task 6: Render sources, summary, and the data-first comparison table

**Files:**
- Create: `components/probability-dashboard/DataSourceStatus.tsx`
- Create: `components/probability-dashboard/AnalysisSummary.tsx`
- Create: `components/probability-dashboard/ProbabilityComparisonTable.tsx`
- Modify: `components/probability-dashboard/ProbabilityDashboard.tsx`
- Modify: `app/globals.css`
- Modify: `tests/probability-dashboard.test.ts`

**Interfaces:**
- Consumes: successful `AutomaticForwardProbabilityResponse` and Task 4 selectors/formatters.
- Produces: always-visible source provenance, compact summary, top-eight table, and expanded 22-row table.

- [ ] **Step 1: Add failing selector tests for most-likely interval and expanded tails**

Add tests proving:

```typescript
test("most likely interval uses interval probability not an exact spot", () => {
  const mostLikely = mostLikelyInterval(intervalFixture);
  assert.equal(mostLikely.lower_spot, 6.6);
  assert.equal(mostLikely.upper_spot, 6.65);
  assert.equal(mostLikely.interval_probability, 0.141);
});

test("expanded rows include open tails and twenty core buckets", () => {
  const rows = allProbabilityRows(profileFixture);
  assert.equal(rows.length, 22);
  assert.equal(rows[0]?.kind, "lower_tail");
  assert.equal(rows.at(-1)?.kind, "upper_tail");
  assert.equal(rows[0]?.amountRangeKind, "boundary");
});
```

Expected fixtures must include the new backend `strategy_minus_no_hedge` range.

- [ ] **Step 2: Run unit tests and verify RED**

Run:

```bash
pnpm run test:unit
```

Expected: missing exported selector or incorrect expanded row shape.

- [ ] **Step 3: Complete Task 4 selectors to satisfy the tests**

Add `mostLikelyInterval` and a discriminated `ProbabilityTableRow` union. Core rows expose all six approved columns; tail rows expose the boundary spot, probability, boundary amounts, and no fabricated unbounded amount range.

Use this discriminated union:

```typescript
export type ProbabilityTableRow =
  | { kind: "core"; interval: ForwardProbabilityInterval }
  | {
      kind: "lower_tail" | "upper_tail";
      direction: "below" | "above";
      boundarySpot: number;
      probability: number;
      noHedgeBoundaryCny: number;
      forwardBoundaryCny: number;
      amountRangeKind: "boundary";
    };
```

`allProbabilityRows(profile)` returns lower tail, mapped core rows, then upper tail. `mostLikelyInterval(intervals)` reduces by `interval_probability` and keeps the earlier interval on ties.

- [ ] **Step 4: Implement the three presentation components**

`DataSourceStatus` must render forecast aggregation status, each participating source with `matched_maturity_spot`, `weight`, `source_updated_date`, `fetched_at_utc`, `cache_status`, and `source_url`, unavailable sources with `reason_code`, and FRED volatility with its one-year window and cache state.

`AnalysisSummary` must render expected maturity spot, the most-likely interval with interval probability, both expected CNY amounts, and both 50%/90% amount ranges.

`ProbabilityComparisonTable` keeps internal `expanded` state. Collapsed mode receives the top eight rows; expanded mode receives all rows. It includes a `<caption>`, semantic headers, an explanation that collapsed rows are selected by probability, and a button whose labels are “查看完整分布” and “收起完整分布”.

Use these component contracts:

```tsx
type ResponseProps = { response: AutomaticForwardProbabilityResponse };
export function ProbabilityComparisonTable({ response }: ResponseProps) {
  const [expanded, setExpanded] = useState(false);
  const rows = expanded
    ? allProbabilityRows(response.probability_profile)
    : selectCoreIntervals(response.probability_profile.intervals).map(
        (interval) => ({ kind: "core" as const, interval }),
      );
  return (
    <section aria-labelledby="probability-table-title">
      <h2 id="probability-table-title">汇率区间与人民币收款对比</h2>
      <p>{expanded ? "完整分布包含20个核心区间和两个极端尾部。" : "默认显示概率最高的8个区间，并按汇率从低到高排列。"}</p>
      <div className="probability-table-scroll">
        <table className="probability-table">
          <caption>不套保与远期策略在同一到期汇率区间下的结果</caption>
          <thead><tr><th>到期汇率区间</th><th>发生概率</th><th>累计概率</th><th>不套保收款</th><th>远期策略收款</th><th>策略差额</th></tr></thead>
          <tbody>{rows.map((row) => <ProbabilityTableRowView key={rowKey(row)} row={row} />)}</tbody>
        </table>
      </div>
      <button type="button" onClick={() => setExpanded((value) => !value)}>
        {expanded ? "收起完整分布" : "查看完整分布"}
      </button>
    </section>
  );
}
```

Implement `ProbabilityTableRowView` and `rowKey` in the same file. Core difference cells read `interval.strategy_minus_no_hedge`; tail difference cells show “边界差额” calculated only from the two boundary amounts returned for that same boundary spot.

- [ ] **Step 5: Integrate results without changing request behavior**

In `ProbabilityDashboard.tsx`, render the three components only when `response` exists. Preserve and dim existing results while `loading_initial` is replacing stale inputs; keep source status visible during target calculation.

- [ ] **Step 6: Add responsive result styles**

Add styles for source cards, fallback warning, summary grid, horizontally scrollable table, sticky first column on narrow screens, positive/negative difference labels, tail-row treatment, and expand/collapse controls. Color must not be the only indication of a positive or negative difference.

Include these structural rules, then add spacing and typography consistent with the input panel:

```css
.source-grid, .analysis-summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.source-fallback { border-color: #e3aa65; background: #fff7e9; }
.probability-table-scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 16px; }
.probability-table { width: 100%; min-width: 1040px; border-collapse: collapse; }
.probability-table th, .probability-table td { padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: right; }
.difference-positive::before { content: "增加 "; }
.difference-negative::before { content: "减少 "; }
.tail-row { background: #fff8f2; }
@media (max-width: 800px) {
  .probability-table th:first-child, .probability-table td:first-child { position: sticky; left: 0; background: inherit; }
}
```

- [ ] **Step 7: Verify unit tests and full frontend build**

Run:

```bash
pnpm run test:unit
pnpm run build
node --test tests/rendered-html.test.mjs
```

Expected: selector tests pass and the dashboard compiles with all response fields typed.

- [ ] **Step 8: Commit Task 6**

```bash
git add \
  lib/analysis/probabilityDashboard.ts \
  tests/probability-dashboard.test.ts \
  components/probability-dashboard/DataSourceStatus.tsx \
  components/probability-dashboard/AnalysisSummary.tsx \
  components/probability-dashboard/ProbabilityComparisonTable.tsx \
  components/probability-dashboard/ProbabilityDashboard.tsx \
  app/globals.css
git commit -m "feat: show probability comparison results"
```

---

### Task 7: Add target analysis, SVG distribution, and risk states

**Files:**
- Create: `components/probability-dashboard/TargetAnalysisPanel.tsx`
- Create: `components/probability-dashboard/ProbabilityDistributionChart.tsx`
- Create: `components/probability-dashboard/RiskNotices.tsx`
- Modify: `components/probability-dashboard/ProbabilityDashboard.tsx`
- Modify: `app/globals.css`
- Modify: `app/layout.tsx`
- Modify: `tests/rendered-html.test.mjs`

**Interfaces:**
- Consumes: first successful response, unchanged base draft, Task 3 API client, and Task 4 formatting helpers.
- Produces: second-step target request, target probability comparison, accessible SVG chart, and explicit limitation/error states.

- [ ] **Step 1: Add failing static-copy and metadata expectations**

Extend `tests/rendered-html.test.mjs`:

```javascript
assert.match(html, /先查看分析结果，再填写目标人民币金额/);
assert.match(html, /概率分布图作为表格的辅助说明/);
assert.match(html, /结果不构成银行报价、交易建议或收益保证/);
assert.match(html, /数据来自 ING、MUFG 与 FRED/);
assert.match(html, /输入真实远期报价，比较不同汇率区间下的人民币收款结果/);
```

Update `app/layout.tsx` metadata description to the same current product scope rather than multi-product free composition.

- [ ] **Step 2: Run build/rendered test and verify RED**

Run:

```bash
pnpm run build
node --test tests/rendered-html.test.mjs
```

Expected: new target, chart, risk, or metadata copy is absent.

- [ ] **Step 3: Implement `TargetAnalysisPanel`**

The component receives target input, target-loading state, both target probability results, and submit callback. Before calculation it explains why the target is a second step. After calculation it renders:

```text
不套保达到目标：probability_met
远期策略达到目标：probability_met
远期策略相对变化：strategy probability - no-hedge probability（百分点）
```

If `critical_spot` is `null`, display whether the fixed/negative-slope strategy always meets or always misses the target based on `probability_met`; never display a fake critical spot.

Use this component contract and percentage-point calculation:

```tsx
type TargetAnalysisPanelProps = {
  targetCny: number | null;
  loading: boolean;
  error: string | null;
  noHedge: TargetProbability | null;
  strategy: TargetProbability | null;
  onTargetChange: (value: number | null) => void;
  onSubmit: () => void;
};

const percentagePointChange = noHedge && strategy
  ? (strategy.probability_met - noHedge.probability_met) * 100
  : null;
```

- [ ] **Step 4: Implement target request behavior in the parent**

Target submit validates only the positive target, sets `loading_target`, calls `requestForwardProbability(buildRequest(draft, targetCny))`, and replaces the response on success. On target failure, keep the previous response and show the target-specific error. Any base-input edit clears the target result and marks the initial response stale.

Use a separate target error state and this handler:

```tsx
const runTargetAnalysis = async () => {
  if (draft.targetCny === null
    || !Number.isFinite(draft.targetCny)
    || draft.targetCny <= 0) {
    setTargetError("目标人民币金额必须大于 0");
    return;
  }
  setStatus("loading_target");
  setTargetError(null);
  try {
    const nextResponse = await requestForwardProbability(
      buildRequest(draft, draft.targetCny),
    );
    setResponse(nextResponse);
    setStatus("success");
  } catch (error) {
    const message = error instanceof ForwardProbabilityApiError
      ? error.message
      : "目标概率计算失败，请重试。";
    setTargetError(message);
    setStatus("success");
  }
};
```

- [ ] **Step 5: Implement an accessible native SVG probability chart**

`ProbabilityDistributionChart` receives the 20 core intervals and distribution ranges. Draw one bar per interval using `interval_probability`; scale bars from the maximum interval probability; label horizontal spot ticks and vertical probability meaning; mark expected spot and visually bracket 50% and 90% spot ranges. Include a visible heading, explanatory paragraph, `role="img"`, and an `aria-label` summarizing the most-likely interval. Do not recalculate probabilities.

Use a viewBox-based SVG so no canvas observer is needed:

```tsx
const width = 960;
const height = 320;
const margin = { top: 28, right: 24, bottom: 54, left: 58 };
const plotWidth = width - margin.left - margin.right;
const plotHeight = height - margin.top - margin.bottom;
const maximumProbability = Math.max(
  ...intervals.map((interval) => interval.interval_probability),
);
const barWidth = plotWidth / intervals.length;

return (
  <svg
    viewBox={`0 0 ${width} ${height}`}
    role="img"
    aria-label={`最高概率区间为${formatSpot(mostLikely.lower_spot)}至${formatSpot(mostLikely.upper_spot)}，发生概率${formatProbability(mostLikely.interval_probability)}`}
  >
    {intervals.map((interval, index) => {
      const barHeight = interval.interval_probability / maximumProbability * plotHeight;
      return <rect key={interval.lower_spot} x={margin.left + index * barWidth + 1} y={margin.top + plotHeight - barHeight} width={Math.max(1, barWidth - 2)} height={barHeight} />;
    })}
  </svg>
);
```

- [ ] **Step 6: Implement `RiskNotices` and final state banners**

Render backend limitations plus explicit local copy for forecast uncertainty, historical volatility limitations, non-advice status, source fallback, stale caches, and over-hedging. Connection errors must say how to start/retry the local Python service without erasing inputs. Unexpected errors expose no stack trace.

Deduplicate notices before rendering:

```tsx
const notices = Array.from(new Set([
  ...response.limitations,
  ...response.data_sources.forecast.limitations,
  "机构预测可能与实际汇率明显不同。",
  "历史波动率不保证代表未来波动。",
  "结果不构成银行报价、交易建议或收益保证。",
]));
```

- [ ] **Step 7: Complete responsive and accessible styling**

Add target comparison cards, chart container, SVG bar states, risk notice hierarchy, loading indicators, error banners, reduced-motion support, and screen widths for desktop/tablet/mobile. Verify keyboard focus, table scrolling, and that differences include signs/text in addition to color.

Minimum chart and reduced-motion rules:

```css
.probability-chart svg { width: 100%; height: auto; min-width: 680px; }
.probability-chart-scroll { overflow-x: auto; }
.probability-chart rect { fill: var(--teal); }
.probability-chart rect.most-likely { fill: var(--orange); }
.risk-notice-list { display: grid; gap: 8px; padding-left: 20px; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; }
}
```

- [ ] **Step 8: Run full frontend checks**

Run:

```bash
pnpm run lint
pnpm run test
```

Expected: lint passes; TypeScript unit tests pass; site build passes; rendered HTML tests pass.

- [ ] **Step 9: Commit Task 7**

```bash
git add \
  components/probability-dashboard/TargetAnalysisPanel.tsx \
  components/probability-dashboard/ProbabilityDistributionChart.tsx \
  components/probability-dashboard/RiskNotices.tsx \
  components/probability-dashboard/ProbabilityDashboard.tsx \
  app/globals.css app/layout.tsx tests/rendered-html.test.mjs
git commit -m "feat: complete probability dashboard workflow"
```

---

### Task 8: Document, run real local smoke tests, and verify the release candidate

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: completed local FastAPI and frontend workflows.
- Produces: repeatable local startup/testing instructions and final evidence.

- [ ] **Step 1: Update README with the Phase 11 local workflow**

Add a section documenting:

```text
1. Start Python: cd python && ../.venv/bin/uvicorn backend.main:app --reload
2. Start frontend: pnpm dev
3. Open the local URL printed by pnpm.
4. Enter USD receivable, future maturity date, and one or more real forward quotes.
5. Run initial analysis, inspect sources and top-eight table, expand all rows.
6. Enter target CNY and compare target probabilities.
```

Document `NEXT_PUBLIC_FX_API_BASE_URL` with default `http://127.0.0.1:8000`, the local-only nature of this phase, over-hedge behavior, source fallback behavior, and the non-advice disclaimer.

- [ ] **Step 2: Run complete automated verification**

Run from the worktree root:

```bash
cd python
../.venv/bin/python -m pytest tests -q
cd ..
pnpm run lint
pnpm run test
git diff --check
```

Expected: all backend tests pass; frontend lint, unit tests, build, and rendered tests pass; `git diff --check` prints nothing.

- [ ] **Step 3: Start the real local services**

In separate sessions:

```bash
cd python
../.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```bash
pnpm dev
```

Expected: `/health` returns 200 and the frontend prints a local browser URL.

- [ ] **Step 4: Use the in-app browser for the full live workflow**

Verify these exact behaviors with the real API:

1. Initial page contains one forward leg and no assumption-spot input.
2. Add a second forward leg and submit a valid future date.
3. Data sources show ING/MUFG participation or an explicit single-source fallback, plus FRED volatility.
4. Default table contains 8 selected core rows ordered by spot.
5. Expanded table contains 22 rows: 20 core plus two open tails.
6. Target amount triggers a second request and shows both probabilities and their percentage-point difference.
7. A 120% forward total shows an over-hedge warning but still analyzes.
8. Stopping Python produces a connection error while preserving input.
9. At desktop and narrow width, labels, table scrolling, focus, and chart remain usable.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md
git commit -m "docs: explain local probability dashboard"
```

- [ ] **Step 6: Perform final clean-tree verification**

Run:

```bash
cd python
../.venv/bin/python -m pytest tests -q
cd ..
pnpm run lint
pnpm run test
git status --short --branch
```

Expected: all checks pass and the branch has no uncommitted files.
