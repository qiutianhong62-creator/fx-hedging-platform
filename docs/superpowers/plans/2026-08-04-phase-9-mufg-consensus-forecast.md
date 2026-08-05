# Phase 9 MUFG Consensus Forecast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing ING-only USD/CNY maturity estimate into a traceable ING + MUFG equal-weight consensus with explicit single-source fallback.

**Architecture:** Keep web parsing, cache handling, per-institution date matching, and multi-institution aggregation as separate layers. Each institution produces an independently matched maturity estimate; the aggregate service averages successful results or reports a transparent fallback without changing the probability formulas used downstream.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, httpx, stdlib `HTMLParser`, `Decimal`, pytest

## Global Constraints

- Only `USD/CNY` is supported, quoted as `CNY per 1 USD`.
- User maturity dates must be after the valuation date and no more than 365 days ahead.
- Read only the official public ING and MUFG forecast pages; do not add login, PDF parsing, scraping services, or new Python dependencies.
- Match each institution to the user maturity date independently before aggregation.
- When both sources succeed, use weights `0.5` and `0.5`; when only one succeeds, use weight `1.0` and mark `single_source_fallback`.
- Round the final consensus spot to at most six decimal places using decimal arithmetic.
- If all sources fail only because of horizon coverage, raise `forecast_horizon_insufficient`; otherwise raise `forecast_sources_unavailable`.
- Keep independent 24-hour normal caches and seven-day network-only stale fallbacks; reject source content older than 45 days.
- Never replace missing institutional forecasts with spot, a fixed default, or random data.
- Automated tests must not access the real network.
- Full probability curves, accuracy weighting, institution-disagreement scoring, and additional institutions are outside Phase 9.

---

## File map

### New files

- `python/backend/forecast/quarters.py` — shared quarter-label parsing for ING and MUFG.
- `python/backend/forecast/mufg.py` — MUFG official-page parser and HTTP provider.
- `python/backend/forecast/institution.py` — one-institution cache, freshness, FRED-anchor, and maturity-matching workflow.
- `python/tests/backend/test_mufg_forecast.py` — fixed-HTML MUFG parser/provider tests.
- `python/tests/backend/test_institution_forecast_service.py` — common single-source behavior for ING and MUFG.

### Modified files

- `python/backend/forecast/ing.py` — use the shared quarter parser.
- `python/backend/forecast/matcher.py` — accept an institution name instead of hard-coding `ING` in anchors.
- `python/backend/forecast/cache.py` — validate caller-supplied source identity and expose independent ING/MUFG default paths.
- `python/backend/forecast/types.py` — add the internal single-institution maturity result.
- `python/backend/forecast/errors.py` — make source errors institution-neutral and add the aggregate unavailable error.
- `python/backend/forecast/schemas.py` — move matching into each source and expose weights plus unavailable sources.
- `python/backend/forecast/service.py` — aggregate two `InstitutionForecastService` instances.
- `python/backend/routes/forecast.py` — construct ING and MUFG providers with separate caches.
- `python/tests/backend/test_ing_forecast.py` — retain ING regression coverage after shared parser extraction.
- `python/tests/backend/test_forecast_matcher.py` — verify institution-specific anchors.
- `python/tests/backend/test_forecast_cache.py` — verify identity validation and cache isolation.
- `python/tests/backend/test_maturity_forecast_service.py` — replace single-source tests with consensus and fallback tests.
- `python/tests/backend/test_maturity_forecast_api.py` — verify the upgraded public response and aggregate error.
- `python/tests/backend/test_automatic_no_hedge_probability_service.py` — use a two-source forecast fixture.
- `python/tests/backend/test_automatic_no_hedge_probability_api.py` — assert consensus provenance survives serialization.
- `python/tests/backend/test_automatic_forward_strategy_probability_service.py` — assert consensus forecast use.
- `python/tests/backend/test_automatic_forward_strategy_probability_api.py` — assert consensus provenance survives serialization.
- `README.md` — explain the two-source forecast and a manual Swagger test.

---

### Task 1: Generalize shared quarter parsing and maturity matching

**Files:**
- Create: `python/backend/forecast/quarters.py`
- Modify: `python/backend/forecast/ing.py`
- Modify: `python/backend/forecast/matcher.py`
- Test: `python/tests/backend/test_ing_forecast.py`
- Test: `python/tests/backend/test_forecast_matcher.py`

**Interfaces:**
- Consumes: `ForecastSourceInvalidError`, `ForecastPoint`, `ForecastAnchor`, and `ForecastMatch`.
- Produces: `parse_quarter_end(label: str, patterns: tuple[re.Pattern[str], ...]) -> date` and `match_maturity_forecast(..., institution: str = "ING", forecast_points: Sequence[ForecastPoint], fred_anchor: ForecastAnchor | None = None) -> ForecastMatch`.

- [ ] **Step 1: Add failing tests for shared quarter formats and institution-specific anchors**

Add these cases while retaining every existing test:

```python
# python/tests/backend/test_ing_forecast.py
from backend.forecast.quarters import parse_quarter_end


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("3Q26F", date(2026, 9, 30)),
        ("Q3 2026", date(2026, 9, 30)),
        ("Q4 2026", date(2026, 12, 31)),
    ],
)
def test_shared_quarter_parser_supports_ing_and_mufg_labels(
    label: str,
    expected: date,
) -> None:
    assert parse_quarter_end(label) == expected


@pytest.mark.parametrize("label", ["Q5 2026", "2026 Q3", "", "3Q26"])
def test_shared_quarter_parser_rejects_unknown_labels(label: str) -> None:
    with pytest.raises(ForecastSourceInvalidError):
        parse_quarter_end(label)
```

```python
# python/tests/backend/test_forecast_matcher.py
def test_matcher_labels_direct_and_interpolated_anchors_with_institution() -> None:
    points = (
        ForecastPoint(date(2026, 9, 30), 6.70),
        ForecastPoint(date(2026, 12, 31), 6.60),
    )

    direct = match_maturity_forecast(
        valuation_date=date(2026, 7, 18),
        maturity_date=date(2026, 9, 30),
        institution="MUFG",
        forecast_points=points,
    )
    between = match_maturity_forecast(
        valuation_date=date(2026, 7, 18),
        maturity_date=date(2026, 11, 15),
        institution="MUFG",
        forecast_points=points,
    )

    assert [item.source for item in direct.anchors] == ["MUFG"]
    assert [item.source for item in between.anchors] == ["MUFG", "MUFG"]
```

- [ ] **Step 2: Run the focused tests and confirm they fail for the intended reasons**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest \
  python/tests/backend/test_ing_forecast.py \
  python/tests/backend/test_forecast_matcher.py -v
```

Expected: FAIL because `backend.forecast.quarters` does not exist and the matcher has no `institution`/`forecast_points` parameters.

- [ ] **Step 3: Add the shared parser and generalize matcher anchors**

Create `python/backend/forecast/quarters.py`:

```python
import re
from datetime import date

from backend.forecast.errors import ForecastSourceInvalidError


QUARTER_PATTERNS = (
    re.compile(r"([1-4])Q(\d{2})F"),
    re.compile(r"Q([1-4])\s+(\d{4})"),
)


def parse_quarter_end(label: str) -> date:
    cleaned = " ".join(label.split())
    for index, pattern in enumerate(QUARTER_PATTERNS):
        match = pattern.fullmatch(cleaned)
        if match is None:
            continue
        quarter = int(match.group(1))
        raw_year = int(match.group(2))
        year = 2000 + raw_year if index == 0 else raw_year
        month, day = {
            1: (3, 31),
            2: (6, 30),
            3: (9, 30),
            4: (12, 31),
        }[quarter]
        return date(year, month, day)
    raise ForecastSourceInvalidError()
```

In `python/backend/forecast/ing.py`, delete `QUARTER_PATTERN` and the local `parse_quarter_label`, import `parse_quarter_end`, and replace:

```python
point_date = parse_quarter_label(label)
```

with:

```python
point_date = parse_quarter_end(label)
```

In `python/backend/forecast/matcher.py`, rename the collection parameter and use the supplied institution for every institution anchor:

```python
def match_maturity_forecast(
    *,
    valuation_date: date,
    maturity_date: date,
    forecast_points: Sequence[ForecastPoint],
    institution: str = "ING",
    fred_anchor: ForecastAnchor | None = None,
) -> ForecastMatch:
    validate_maturity_date(valuation_date, maturity_date)
    future_points = tuple(
        item for item in forecast_points if item.date > valuation_date
    )
    if not future_points or maturity_date > future_points[-1].date:
        raise ForecastHorizonInsufficientError()

    for point in future_points:
        if point.date == maturity_date:
            anchor = ForecastAnchor(institution, point.date, point.spot)
            return ForecastMatch(
                expected_spot=point.spot,
                method="direct",
                is_system_estimate=False,
                day_weight=None,
                anchors=(anchor,),
            )

    first = future_points[0]
    if maturity_date < first.date:
        if fred_anchor is None:
            raise ForecastAnchorRequiredError()
        if fred_anchor.date > valuation_date or fred_anchor.date >= maturity_date:
            raise ForecastSourceInvalidError()
        return _interpolate(
            maturity_date,
            fred_anchor,
            ForecastAnchor(institution, first.date, first.spot),
        )

    for before, after in zip(future_points, future_points[1:]):
        if before.date < maturity_date < after.date:
            return _interpolate(
                maturity_date,
                ForecastAnchor(institution, before.date, before.spot),
                ForecastAnchor(institution, after.date, after.spot),
            )
    raise ForecastHorizonInsufficientError()
```

Update existing call sites and tests from `ing_points=` to `forecast_points=`.

- [ ] **Step 4: Run focused and full regression tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest \
  python/tests/backend/test_ing_forecast.py \
  python/tests/backend/test_forecast_matcher.py \
  python/tests/backend/test_maturity_forecast_service.py -v
```

Expected: all selected tests PASS and existing ING results remain unchanged.

- [ ] **Step 5: Commit the generalized forecast primitives**

```bash
git add python/backend/forecast/quarters.py \
  python/backend/forecast/ing.py \
  python/backend/forecast/matcher.py \
  python/tests/backend/test_ing_forecast.py \
  python/tests/backend/test_forecast_matcher.py \
  python/tests/backend/test_maturity_forecast_service.py
git commit -m "refactor: generalize forecast matching primitives"
```

---

### Task 2: Add the MUFG parser and HTTP provider

**Files:**
- Create: `python/backend/forecast/mufg.py`
- Create: `python/tests/backend/test_mufg_forecast.py`

**Interfaces:**
- Consumes: `parse_quarter_end`, `ForecastFetchError`, `ForecastSourceInvalidError`, `ForecastPoint`, and `InstitutionForecastSnapshot`.
- Produces: `MUFG_FORECAST_URL`, `parse_mufg_forecast_html(html_text: str, retrieved_at_utc: datetime) -> InstitutionForecastSnapshot`, and `MufgForecastProvider.fetch(retrieved_at_utc) -> InstitutionForecastSnapshot`.

- [ ] **Step 1: Write fixed-HTML parser and provider failure tests**

Create `python/tests/backend/test_mufg_forecast.py` with a realistic minimal fixture and explicit invalid variants:

```python
from datetime import date, datetime, timezone

import httpx
import pytest

from backend.forecast.errors import ForecastFetchError, ForecastSourceInvalidError
from backend.forecast.mufg import (
    MUFG_FORECAST_URL,
    MufgForecastProvider,
    parse_mufg_forecast_html,
)


RETRIEVED_AT = datetime(2026, 8, 4, 10, tzinfo=timezone.utc)
VALID_HTML = """
<html><body>
  <p>Latest FX forecast update: 03 July 2026</p>
  <h2>FX Rates</h2>
  <table>
    <thead><tr><th>Currency Pair</th><th>Q3 2026</th><th>Q4 2026</th><th>Q1 2027</th><th>Q2 2027</th></tr></thead>
    <tbody><tr><td>USD/CNY</td><td>6.7000</td><td>6.6500</td><td>6.6000</td><td>6.6000</td></tr></tbody>
  </table>
</body></html>
"""


def test_parse_mufg_forecast_html_returns_valid_snapshot() -> None:
    result = parse_mufg_forecast_html(VALID_HTML, RETRIEVED_AT)

    assert result.institution == "MUFG"
    assert result.currency_pair == "USD/CNY"
    assert result.source_url == MUFG_FORECAST_URL
    assert result.source_updated_date == date(2026, 7, 3)
    assert result.fetched_at_utc == RETRIEVED_AT
    assert [(item.date, item.spot) for item in result.points] == [
        (date(2026, 9, 30), 6.7),
        (date(2026, 12, 31), 6.65),
        (date(2027, 3, 31), 6.6),
        (date(2027, 6, 30), 6.6),
    ]


@pytest.mark.parametrize(
    "html_text",
    [
        VALID_HTML.replace("USD/CNY", "EUR/USD"),
        VALID_HTML.replace("</tbody>", "<tr><td>USD/CNY</td><td>6.7</td><td>6.6</td><td>6.5</td><td>6.4</td></tr></tbody>"),
        VALID_HTML.replace("<td>6.7000</td>", "<td>not-a-number</td>"),
        VALID_HTML.replace("<td>6.7000</td>", "<td>-1</td>"),
        VALID_HTML.replace("<td>6.7000</td>", "<td>inf</td>"),
        VALID_HTML.replace("Latest FX forecast update: 03 July 2026", ""),
        VALID_HTML.replace("03 July 2026", "31 February 2026"),
        VALID_HTML.replace("03 July 2026", "03 July 2027"),
        VALID_HTML.replace("Q4 2026", "Q3 2026"),
    ],
)
def test_parse_mufg_forecast_html_rejects_untrusted_content(
    html_text: str,
) -> None:
    with pytest.raises(ForecastSourceInvalidError):
        parse_mufg_forecast_html(html_text, RETRIEVED_AT)


def test_parse_mufg_requires_timezone_and_two_future_points() -> None:
    with pytest.raises(ForecastSourceInvalidError):
        parse_mufg_forecast_html(VALID_HTML, RETRIEVED_AT.replace(tzinfo=None))
    with pytest.raises(ForecastSourceInvalidError):
        parse_mufg_forecast_html(
            VALID_HTML.replace("Q1 2027", "Q1 2026").replace("Q2 2027", "Q2 2026"),
            RETRIEVED_AT,
        )


@pytest.mark.parametrize("error", [httpx.TimeoutException("timeout"), httpx.ConnectError("offline")])
def test_mufg_provider_converts_http_errors(error: httpx.HTTPError) -> None:
    class FailingClient:
        def get(self, *args, **kwargs):
            raise error

    with pytest.raises(ForecastFetchError):
        MufgForecastProvider(http_client=FailingClient()).fetch(RETRIEVED_AT)
```

Also add a fake 302/200 response test proving the provider uses `follow_redirects=True`, the official URL, timeout, and user agent without making a network call.

- [ ] **Step 2: Run the MUFG tests and confirm the module is missing**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_mufg_forecast.py -v
```

Expected: FAIL with `ModuleNotFoundError: backend.forecast.mufg`.

- [ ] **Step 3: Implement strict MUFG HTML parsing and provider behavior**

Create `python/backend/forecast/mufg.py`. The implementation must:

```python
MUFG_FORECAST_URL = "https://mufgresearch.com/forecasts/"
UPDATED_PATTERN = re.compile(
    r"Latest\s+FX\s+forecast\s+update:\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
)
```

Use one `HTMLParser` subclass that records normalized table headers/rows and surrounding page text. `parse_mufg_forecast_html` must apply all of these checks before constructing the snapshot:

```python
def parse_mufg_forecast_html(
    html_text: str,
    retrieved_at_utc: datetime,
) -> InstitutionForecastSnapshot:
    if retrieved_at_utc.tzinfo is None:
        raise ForecastSourceInvalidError()
    parser = _MufgForecastParser()
    parser.feed(html_text)
    parser.close()
    candidates = parser.usd_cny_candidates()
    if len(candidates) != 1:
        raise ForecastSourceInvalidError()
    headers, values = candidates[0]
    if len(headers) != len(values) or len(headers) < 3:
        raise ForecastSourceInvalidError()

    points = tuple(
        ForecastPoint(parse_quarter_end(label), _positive_finite(raw_value))
        for label, raw_value in zip(headers[1:], values[1:])
    )
    point_dates = [item.date for item in points]
    if point_dates != sorted(set(point_dates)):
        raise ForecastSourceInvalidError()
    if sum(item.date > retrieved_at_utc.date() for item in points) < 2:
        raise ForecastSourceInvalidError()

    updated_date = _parse_full_updated_date(
        " ".join(parser.page_text_parts),
        retrieved_at_utc.date(),
    )
    return InstitutionForecastSnapshot(
        institution="MUFG",
        currency_pair="USD/CNY",
        source_url=MUFG_FORECAST_URL,
        source_updated_date=updated_date,
        fetched_at_utc=retrieved_at_utc,
        points=points,
    )
```

The table selector must require a nearby `FX Rates` heading and a unique normalized `USD/CNY` row. `_positive_finite` must reject empty, non-numeric, infinite, NaN, and non-positive values. `_parse_full_updated_date` must reject missing, invalid, or future dates. Implement `MufgForecastProvider` with the same 10-second timeout, redirects, user agent, and `ForecastFetchError` mapping as ING.

- [ ] **Step 4: Run MUFG and ING parser regressions**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest \
  python/tests/backend/test_mufg_forecast.py \
  python/tests/backend/test_ing_forecast.py -v
```

Expected: all tests PASS; no real HTTP requests occur.

- [ ] **Step 5: Commit the MUFG source adapter**

```bash
git add python/backend/forecast/mufg.py \
  python/tests/backend/test_mufg_forecast.py
git commit -m "feat: add MUFG USD CNY forecast provider"
```

---

### Task 3: Make forecast caches institution-aware and independent

**Files:**
- Modify: `python/backend/forecast/cache.py`
- Modify: `python/tests/backend/test_forecast_cache.py`

**Interfaces:**
- Consumes: `InstitutionForecastSnapshot` and the official source constants from ING/MUFG.
- Produces: `JsonForecastCache(path, *, institution, source_url)`, `default_ing_forecast_cache_path()`, and `default_mufg_forecast_cache_path()`.

- [ ] **Step 1: Write failing identity and path-isolation tests**

Replace test construction with explicit source identity and add:

```python
def test_ing_and_mufg_default_cache_paths_are_independent() -> None:
    assert default_ing_forecast_cache_path().name == "ing-usdcny-forecast.json"
    assert default_mufg_forecast_cache_path().name == "mufg-usdcny-forecast.json"
    assert default_ing_forecast_cache_path() != default_mufg_forecast_cache_path()


def test_cache_rejects_snapshot_for_another_institution(tmp_path: Path) -> None:
    path = tmp_path / "forecast.json"
    ing_cache = JsonForecastCache(
        path,
        institution="ING",
        source_url=ING_FORECAST_URL,
    )
    ing_cache.save(snapshot())

    mufg_cache = JsonForecastCache(
        path,
        institution="MUFG",
        source_url=MUFG_FORECAST_URL,
    )
    assert mufg_cache.load() is None
```

Retain the corrupt JSON, wrong currency pair, duplicate point, nonpositive point, timezone, future source-update, and atomic-save cases for both institution identities through parameterization.

- [ ] **Step 2: Run the cache test and confirm constructor/path failures**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_forecast_cache.py -v
```

Expected: FAIL because cache validation is hard-coded to ING and the two path functions do not exist.

- [ ] **Step 3: Generalize cache validation without weakening it**

Implement the constructor and path helpers:

```python
def _market_data_cache_path(filename: str) -> Path:
    python_root = Path(__file__).resolve().parents[2]
    return python_root / ".cache" / "market-data" / filename


def default_ing_forecast_cache_path() -> Path:
    return _market_data_cache_path("ing-usdcny-forecast.json")


def default_mufg_forecast_cache_path() -> Path:
    return _market_data_cache_path("mufg-usdcny-forecast.json")


class JsonForecastCache:
    def __init__(
        self,
        path: Path,
        *,
        institution: str,
        source_url: str,
    ) -> None:
        self.path = path
        self.institution = institution
        self.source_url = source_url
```

In `load`, replace ING-specific checks with:

```python
if (
    snapshot.institution != self.institution
    or snapshot.currency_pair != "USD/CNY"
    or snapshot.source_url != self.source_url
    or snapshot.fetched_at_utc.tzinfo is None
    or snapshot.source_updated_date > snapshot.fetched_at_utc.date()
    or len(snapshot.points) < 2
    or point_dates != sorted(set(point_dates))
    or any(not isfinite(item.spot) or item.spot <= 0 for item in snapshot.points)
):
    return None
```

Update every `JsonForecastCache` call in existing tests and production code to pass the expected institution and URL. Do not retain `default_forecast_cache_path`; all call sites should name the institution explicitly.

- [ ] **Step 4: Run cache and current service tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest \
  python/tests/backend/test_forecast_cache.py \
  python/tests/backend/test_maturity_forecast_service.py \
  python/tests/backend/test_maturity_forecast_api.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 5: Commit the institution-aware cache layer**

```bash
git add python/backend/forecast/cache.py \
  python/backend/routes/forecast.py \
  python/tests/backend/test_forecast_cache.py \
  python/tests/backend/test_maturity_forecast_service.py
git commit -m "refactor: isolate institutional forecast caches"
```

---

### Task 4: Extract the reusable single-institution maturity service

**Files:**
- Create: `python/backend/forecast/institution.py`
- Modify: `python/backend/forecast/types.py`
- Create: `python/tests/backend/test_institution_forecast_service.py`
- Modify: `python/backend/forecast/service.py`
- Modify: `python/tests/backend/test_maturity_forecast_service.py`

**Interfaces:**
- Consumes: `ForecastProvider`, `JsonForecastCache`, `match_maturity_forecast`, market reference lookup, cache TTL constants, and forecast source errors.
- Produces: `InstitutionMaturityEstimate` and `InstitutionForecastService.get_estimate(valuation_date: date, maturity_date: date, *, now_utc: datetime) -> InstitutionMaturityEstimate`.

- [ ] **Step 1: Write one-source behavioral tests for both institution identities**

Create `python/tests/backend/test_institution_forecast_service.py`. Reuse a parameterized `institution/source_url/cache` fixture and cover:

```python
@pytest.mark.parametrize(
    ("institution", "source_url"),
    [("ING", ING_FORECAST_URL), ("MUFG", MUFG_FORECAST_URL)],
)
def test_single_institution_service_returns_traceable_match(
    tmp_path: Path,
    institution: str,
    source_url: str,
) -> None:
    provider = FakeProvider(snapshot(institution, source_url))
    market = FakeMarketService()
    result = institution_service(
        tmp_path, institution, source_url, provider, market
    ).get_estimate(NOW.date(), date(2026, 11, 15))

    assert result.institution == institution
    assert result.matched.expected_spot == pytest.approx(6.72)
    assert [anchor.source for anchor in result.matched.anchors] == [
        institution,
        institution,
    ]
    assert result.cache_status == "live_fetch"
    assert result.cache_age_hours == 0
    assert result.is_stale is False
```

Add explicit tests for direct matching, FRED anchor before the first point, 24-hour cache hit, network-only stale fallback through seven days, rejection after seven days, future cache refetch, invalid page not hidden by cache, future source update, source older than 45 days, and horizon insufficiency. Assert the same behavior for ING and MUFG.

- [ ] **Step 2: Run the new tests and confirm the service/type are absent**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest \
  python/tests/backend/test_institution_forecast_service.py -v
```

Expected: FAIL because `InstitutionForecastService` and `InstitutionMaturityEstimate` do not exist.

- [ ] **Step 3: Add the internal result type**

Append to `python/backend/forecast/types.py`:

```python
@dataclass(frozen=True)
class InstitutionMaturityEstimate:
    institution: str
    matched: ForecastMatch
    snapshot: InstitutionForecastSnapshot
    cache_status: str
    cache_age_hours: float
    is_stale: bool
```

- [ ] **Step 4: Move single-source retrieval, freshness, and matching into the new service**

Create `python/backend/forecast/institution.py` with these public constants and methods:

```python
NORMAL_CACHE_TTL = timedelta(hours=24)
FALLBACK_CACHE_TTL = timedelta(days=7)
MAX_SOURCE_AGE_DAYS = 45


class InstitutionForecastService:
    def __init__(
        self,
        *,
        provider: ForecastProvider,
        cache: JsonForecastCache,
        market_history_service: MarketHistoryLookup,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._market_history_service = market_history_service

    def get_estimate(
        self,
        valuation_date: date,
        maturity_date: date,
        *,
        now_utc: datetime,
    ) -> InstitutionMaturityEstimate:
        snapshot, cache_status = self._get_snapshot(now_utc)
        source_age_days = (valuation_date - snapshot.source_updated_date).days
        if source_age_days < 0:
            raise ForecastSourceInvalidError()
        if source_age_days > MAX_SOURCE_AGE_DAYS:
            raise ForecastSourceStaleError()
        if cache_status == "live_fetch":
            self._cache.save(snapshot)

        try:
            matched = match_maturity_forecast(
                valuation_date=valuation_date,
                maturity_date=maturity_date,
                institution=snapshot.institution,
                forecast_points=snapshot.points,
            )
        except ForecastAnchorRequiredError:
            reference = self._market_history_service.get_summary().market_reference
            matched = match_maturity_forecast(
                valuation_date=valuation_date,
                maturity_date=maturity_date,
                institution=snapshot.institution,
                forecast_points=snapshot.points,
                fred_anchor=ForecastAnchor(
                    source="FRED",
                    date=reference.observation_date,
                    spot=reference.spot,
                ),
            )

        cache_age_hours = max(
            0.0,
            (now_utc - snapshot.fetched_at_utc).total_seconds() / 3600,
        )
        return InstitutionMaturityEstimate(
            institution=snapshot.institution,
            matched=matched,
            snapshot=snapshot,
            cache_status=cache_status,
            cache_age_hours=cache_age_hours,
            is_stale=cache_status == "stale_fallback",
        )
```

Implement `_get_snapshot` by moving the current 24-hour/7-day logic unchanged. It must catch only `ForecastFetchError`; `ForecastSourceInvalidError` must propagate and may not use stale cache.

Temporarily make existing `MaturityForecastService` delegate to one `InstitutionForecastService` so all old endpoint behavior remains green until Task 5. Do not duplicate cache or matching logic in `service.py`.

- [ ] **Step 5: Run single-institution and existing service regressions**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest \
  python/tests/backend/test_institution_forecast_service.py \
  python/tests/backend/test_maturity_forecast_service.py \
  python/tests/backend/test_maturity_forecast_api.py -v
```

Expected: all selected tests PASS and the legacy one-source response remains intact for one more commit.

- [ ] **Step 6: Commit the single-institution service boundary**

```bash
git add python/backend/forecast/institution.py \
  python/backend/forecast/types.py \
  python/backend/forecast/service.py \
  python/tests/backend/test_institution_forecast_service.py \
  python/tests/backend/test_maturity_forecast_service.py
git commit -m "refactor: extract institutional forecast service"
```

---

### Task 5: Build the equal-weight consensus and fallback response

**Files:**
- Modify: `python/backend/forecast/errors.py`
- Modify: `python/backend/forecast/schemas.py`
- Modify: `python/backend/forecast/service.py`
- Modify: `python/tests/backend/test_maturity_forecast_service.py`

**Interfaces:**
- Consumes: two named `InstitutionForecastService` instances and their `InstitutionMaturityEstimate` values.
- Produces: aggregate `MaturityForecastService.get_estimate(maturity_date: date) -> MaturityForecastResponse`, `ForecastSourcesUnavailableError`, and stable unavailable-source reason codes.

- [ ] **Step 1: Replace legacy service tests with consensus, fallback, and all-failed cases**

Use fake institution services whose calls and outcomes are deterministic. Required core tests:

```python
def test_two_sources_are_matched_first_then_equal_weighted() -> None:
    ing = FakeInstitutionService(result=estimate("ING", 6.68))
    mufg = FakeInstitutionService(result=estimate("MUFG", 6.62))

    result = aggregate_service(ing, mufg).get_estimate(MATURITY_DATE)

    assert result.expected_maturity_spot == 6.65
    assert result.source_count == 2
    assert result.aggregation_status == "equal_weight_consensus"
    assert result.is_consensus_forecast is True
    assert [(item.institution, item.matched_maturity_spot, item.weight) for item in result.sources] == [
        ("ING", 6.68, 0.5),
        ("MUFG", 6.62, 0.5),
    ]
    assert result.unavailable_sources == []


def test_consensus_rounds_decimal_result_to_six_places() -> None:
    result = aggregate_service(
        FakeInstitutionService(result=estimate("ING", 6.1234567)),
        FakeInstitutionService(result=estimate("MUFG", 6.2345678)),
    ).get_estimate(MATURITY_DATE)
    assert result.expected_maturity_spot == 6.179012


@pytest.mark.parametrize(
    ("failed_name", "error", "reason_code"),
    [
        ("ING", ForecastSourceUnavailableError(), "fetch_failed"),
        ("MUFG", ForecastSourceInvalidError(), "source_invalid"),
        ("ING", ForecastSourceStaleError(), "source_stale"),
        ("MUFG", ForecastHorizonInsufficientError(), "horizon_insufficient"),
    ],
)
def test_one_failed_source_returns_traceable_fallback(
    failed_name: str,
    error: Exception,
    reason_code: str,
) -> None:
    result = aggregate_with_one_failure(failed_name, error).get_estimate(MATURITY_DATE)
    assert result.source_count == 1
    assert result.aggregation_status == "single_source_fallback"
    assert result.is_consensus_forecast is False
    assert result.sources[0].weight == 1.0
    assert result.unavailable_sources[0].institution == failed_name
    assert result.unavailable_sources[0].reason_code == reason_code
```

Also test: both horizon failures raise `ForecastHorizonInsufficientError`; any other pair or mixed failure raises `ForecastSourcesUnavailableError`; invalid maturity is rejected before either institution service is called; limits differ between consensus and fallback.

- [ ] **Step 2: Run service tests and confirm legacy schema/status failures**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests/backend/test_maturity_forecast_service.py -v
```

Expected: FAIL because the response still exposes `single_source_trial`, top-level `matching`, and no unavailable sources.

- [ ] **Step 3: Make public errors source-neutral and add the aggregate error**

Update `python/backend/forecast/errors.py`:

```python
class ForecastHorizonInsufficientError(ForecastError):
    code = "forecast_horizon_insufficient"
    message = "机构预测期限不足，无法覆盖该到期日"
    status_code = 503


class ForecastSourceUnavailableError(ForecastError):
    code = "forecast_source_unavailable"
    message = "机构预测数据暂时不可用，请稍后重试"
    status_code = 503


class ForecastSourcesUnavailableError(ForecastError):
    code = "forecast_sources_unavailable"
    message = "所有机构预测数据暂时不可用，请稍后重试"
    status_code = 503


class ForecastSourceInvalidError(ForecastError):
    code = "forecast_source_invalid"
    message = "机构预测页面格式异常，请稍后重试"
    status_code = 502


class ForecastSourceStaleError(ForecastError):
    code = "forecast_source_stale"
    message = "机构预测已超过45天未更新"
    status_code = 503
```

- [ ] **Step 4: Upgrade the response schema**

Replace the institution and aggregate response models in `python/backend/forecast/schemas.py`:

```python
InstitutionName = Literal["ING", "MUFG"]
UnavailableReason = Literal[
    "fetch_failed",
    "source_invalid",
    "source_stale",
    "horizon_insufficient",
]


class ForecastAnchorResponse(BaseModel):
    source: Literal["ING", "MUFG", "FRED"]
    date: date
    spot: float


class InstitutionForecastSourceResponse(BaseModel):
    institution: InstitutionName
    matched_maturity_spot: float
    weight: Literal[0.5, 1.0]
    matching: ForecastMatchingResponse
    source_updated_date: date
    source_url: str
    forecast_points: list[ForecastPointResponse]
    cache_status: CacheStatus
    fetched_at_utc: datetime
    cache_age_hours: float
    is_stale: bool


class UnavailableForecastSourceResponse(BaseModel):
    institution: InstitutionName
    reason_code: UnavailableReason


class MaturityForecastResponse(BaseModel):
    status: Literal["available"] = "available"
    currency_pair: Literal["USD/CNY"] = "USD/CNY"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    valuation_date: date
    maturity_date: date
    expected_maturity_spot: float
    source_count: Literal[1, 2]
    aggregation_status: Literal[
        "equal_weight_consensus",
        "single_source_fallback",
    ]
    is_consensus_forecast: bool
    sources: list[InstitutionForecastSourceResponse]
    unavailable_sources: list[UnavailableForecastSourceResponse]
    limitations: list[str]
```

Do not retain the top-level `matching` field.

- [ ] **Step 5: Implement aggregation, reason mapping, Decimal averaging, and limitations**

In `python/backend/forecast/service.py`, validate maturity once before any sources, call both sources even if the first fails, and catch only known source-level errors:

```python
REASON_CODES = {
    ForecastSourceUnavailableError: "fetch_failed",
    ForecastSourceInvalidError: "source_invalid",
    ForecastSourceStaleError: "source_stale",
    ForecastHorizonInsufficientError: "horizon_insufficient",
}

CONSENSUS_LIMITATIONS = [
    "当前仅包含ING和MUFG两家机构，不代表完整市场共识。",
    "两家机构暂时等权，没有使用历史准确率。",
    "插值结果是系统估算，不是机构对该具体日期的直接预测。",
    "机构预测可能与实际结果明显不同。",
]


class MaturityForecastService:
    def __init__(
        self,
        *,
        institution_services: tuple[
            tuple[str, InstitutionForecastService],
            tuple[str, InstitutionForecastService],
        ],
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self._institution_services = institution_services
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
        now = self._now_utc()
        validate_maturity_date(now.date(), maturity_date)
        successes: list[InstitutionMaturityEstimate] = []
        failures: list[UnavailableForecastSourceResponse] = []
        for institution, service in self._institution_services:
            try:
                successes.append(
                    service.get_estimate(
                        now.date(),
                        maturity_date,
                        now_utc=now,
                    )
                )
            except tuple(REASON_CODES) as exc:
                failures.append(
                    UnavailableForecastSourceResponse(
                        institution=institution,
                        reason_code=REASON_CODES[type(exc)],
                    )
                )

        if not successes:
            if failures and all(
                item.reason_code == "horizon_insufficient" for item in failures
            ):
                raise ForecastHorizonInsufficientError()
            raise ForecastSourcesUnavailableError()

        weight = Decimal("0.5") if len(successes) == 2 else Decimal("1")
        expected = sum(
            Decimal(str(item.matched.expected_spot)) * weight
            for item in successes
        ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        return _build_response(
            valuation_date=now.date(),
            maturity_date=maturity_date,
            expected_maturity_spot=float(expected),
            estimates=successes,
            failures=failures,
            weight=float(weight),
        )
```

`_build_response` must map every snapshot point, match anchor, cache field, matched spot, and weight into the schema. Use `equal_weight_consensus`/`True` and `CONSENSUS_LIMITATIONS` for two successes. For one success, use `single_source_fallback`/`False` and append:

```python
[
    "当前只有一家机构可用，结果不是多机构综合预测。",
    "不可用机构及原因已列在unavailable_sources中。",
    "另一机构恢复后，系统会重新使用50%/50%等权综合。",
]
```

- [ ] **Step 6: Run aggregate service tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest \
  python/tests/backend/test_maturity_forecast_service.py \
  python/tests/backend/test_institution_forecast_service.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 7: Commit the consensus domain service**

```bash
git add python/backend/forecast/errors.py \
  python/backend/forecast/schemas.py \
  python/backend/forecast/service.py \
  python/tests/backend/test_maturity_forecast_service.py
git commit -m "feat: aggregate ING and MUFG forecasts"
```

---

### Task 6: Wire the two sources into FastAPI and preserve them downstream

**Files:**
- Modify: `python/backend/routes/forecast.py`
- Modify: `python/tests/backend/test_maturity_forecast_api.py`
- Modify: `python/tests/backend/test_automatic_no_hedge_probability_service.py`
- Modify: `python/tests/backend/test_automatic_no_hedge_probability_api.py`
- Modify: `python/tests/backend/test_automatic_forward_strategy_probability_service.py`
- Modify: `python/tests/backend/test_automatic_forward_strategy_probability_api.py`

**Interfaces:**
- Consumes: `IngForecastProvider`, `MufgForecastProvider`, two institution caches, `InstitutionForecastService`, and aggregate `MaturityForecastService`.
- Produces: the upgraded existing endpoint and unchanged probability formulas fed by the consensus `expected_maturity_spot`.

- [ ] **Step 1: Upgrade API and automatic-analysis fixtures before production wiring**

Create a shared two-source response fixture with:

```python
{
    "valuation_date": VALUATION_DATE,
    "maturity_date": MATURITY_DATE,
    "expected_maturity_spot": 6.65,
    "source_count": 2,
    "aggregation_status": "equal_weight_consensus",
    "is_consensus_forecast": True,
    "sources": [
        {
            "institution": "ING",
            "matched_maturity_spot": 6.68,
            "weight": 0.5,
            "matching": {
                "method": "interpolated",
                "is_system_estimate": True,
                "day_weight": 0.5,
                "anchors": [
                    {"source": "ING", "date": "2026-09-30", "spot": 6.70},
                    {"source": "ING", "date": "2026-12-31", "spot": 6.66},
                ],
            },
            "source_updated_date": "2026-07-16",
            "source_url": "https://think.ing.com/forecasts/",
            "forecast_points": [
                {"date": "2026-09-30", "spot": 6.70},
                {"date": "2026-12-31", "spot": 6.66},
            ],
            "cache_status": "daily_cache",
            "fetched_at_utc": "2026-08-04T10:00:00Z",
            "cache_age_hours": 2.0,
            "is_stale": False,
        },
        {
            "institution": "MUFG",
            "matched_maturity_spot": 6.62,
            "weight": 0.5,
            "matching": {
                "method": "interpolated",
                "is_system_estimate": True,
                "day_weight": 0.5,
                "anchors": [
                    {"source": "MUFG", "date": "2026-09-30", "spot": 6.65},
                    {"source": "MUFG", "date": "2026-12-31", "spot": 6.59},
                ],
            },
            "source_updated_date": "2026-07-03",
            "source_url": "https://mufgresearch.com/forecasts/",
            "forecast_points": [
                {"date": "2026-09-30", "spot": 6.65},
                {"date": "2026-12-31", "spot": 6.59},
            ],
            "cache_status": "live_fetch",
            "fetched_at_utc": "2026-08-04T10:00:00Z",
            "cache_age_hours": 0.0,
            "is_stale": False,
        },
    ],
    "unavailable_sources": [],
    "limitations": ["当前仅包含ING和MUFG两家机构，不代表完整市场共识。"],
}
```

Update assertions in both automatic service suites so expected spot and amount use `6.65`, and assert the returned `data_sources.forecast.sources` contains `ING` and `MUFG` with weights `0.5`. In both automatic API suites assert the same serialized provenance. Add the new `ForecastSourcesUnavailableError` code to API error parameterizations.

- [ ] **Step 2: Run API/downstream tests and confirm the route still builds one source**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest \
  python/tests/backend/test_maturity_forecast_api.py \
  python/tests/backend/test_automatic_no_hedge_probability_service.py \
  python/tests/backend/test_automatic_no_hedge_probability_api.py \
  python/tests/backend/test_automatic_forward_strategy_probability_service.py \
  python/tests/backend/test_automatic_forward_strategy_probability_api.py -v
```

Expected: FAIL at the route factory and legacy one-source response assertions; probability formulas themselves should need no changes.

- [ ] **Step 3: Construct two institution services in the existing route factory**

Replace `get_maturity_forecast_service` in `python/backend/routes/forecast.py` with:

```python
@lru_cache
def get_maturity_forecast_service() -> MaturityForecastService:
    market_history_service = get_market_history_service()
    ing = InstitutionForecastService(
        provider=IngForecastProvider(),
        cache=JsonForecastCache(
            default_ing_forecast_cache_path(),
            institution="ING",
            source_url=ING_FORECAST_URL,
        ),
        market_history_service=market_history_service,
    )
    mufg = InstitutionForecastService(
        provider=MufgForecastProvider(),
        cache=JsonForecastCache(
            default_mufg_forecast_cache_path(),
            institution="MUFG",
            source_url=MUFG_FORECAST_URL,
        ),
        market_history_service=market_history_service,
    )
    return MaturityForecastService(
        institution_services=(("ING", ing), ("MUFG", mufg)),
    )
```

Keep the same URL and dependency name. Do not change `automatic_analysis/service.py`; it already reads only `forecast.valuation_date`, `forecast.expected_maturity_spot`, and forwards the full forecast response.

- [ ] **Step 4: Update endpoint assertions for consensus and fallback**

The forecast API success test must assert:

```python
assert body["expected_maturity_spot"] == 6.65
assert body["source_count"] == 2
assert body["aggregation_status"] == "equal_weight_consensus"
assert body["is_consensus_forecast"] is True
assert [item["institution"] for item in body["sources"]] == ["ING", "MUFG"]
assert [item["weight"] for item in body["sources"]] == [0.5, 0.5]
assert body["sources"][0]["matching"]["method"] == "interpolated"
assert "matching" not in body
assert body["unavailable_sources"] == []
```

Add a single-source fake response and assert `single_source_fallback`, source weight `1.0`, and an unavailable MUFG item with `fetch_failed`.

- [ ] **Step 5: Run all API and downstream tests**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest \
  python/tests/backend/test_maturity_forecast_api.py \
  python/tests/backend/test_automatic_no_hedge_probability_service.py \
  python/tests/backend/test_automatic_no_hedge_probability_api.py \
  python/tests/backend/test_automatic_forward_strategy_probability_service.py \
  python/tests/backend/test_automatic_forward_strategy_probability_api.py -v
```

Expected: all selected tests PASS. Existing probability values change only because the fixture's expected maturity spot changes from `6.72` to `6.65`.

- [ ] **Step 6: Commit route wiring and downstream provenance**

```bash
git add python/backend/routes/forecast.py \
  python/tests/backend/test_maturity_forecast_api.py \
  python/tests/backend/test_automatic_no_hedge_probability_service.py \
  python/tests/backend/test_automatic_no_hedge_probability_api.py \
  python/tests/backend/test_automatic_forward_strategy_probability_service.py \
  python/tests/backend/test_automatic_forward_strategy_probability_api.py
git commit -m "feat: expose consensus forecast across analysis APIs"
```

---

### Task 7: Document, verify, and manually exercise Phase 9

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the completed consensus endpoint and automatic analysis endpoints.
- Produces: user-facing local test instructions and final verification evidence.

- [ ] **Step 1: Update README wording and manual test example**

Replace the final ING-only paragraph with:

```markdown
### 第九阶段：ING + MUFG 综合预测

系统分别读取 ING 与 MUFG 的公开 USD/CNY 季度预测，分别换算到用户到期日，再以 50%/50% 等权生成预计到期汇率。若只有一家来源可用，系统会返回 `single_source_fallback`、100% 权重和另一来源的失败原因；两家都不可用时不会编造预测。

启动后端后，在 `http://127.0.0.1:8000/docs` 测试：

```text
GET /api/v1/forecasts/usd-cny/maturity-estimate
```

把 `maturity_date` 填为当前日期之后 365 天以内、且不超过机构最远预测日期的日期。正常综合结果应看到：

```text
aggregation_status = equal_weight_consensus
source_count = 2
ING weight = 0.5
MUFG weight = 0.5
```

机构预测和概率模型都可能与实际结果明显不同，结果不构成交易或套保建议。
```

Also update the current-features list to mention automatic ING/MUFG maturity forecasts and automatic no-hedge/forward probability analysis.

- [ ] **Step 2: Run format-independent source checks**

Run:

```bash
rg -n "single_source_trial|default_forecast_cache_path|ing_points=" python/backend python/tests README.md
```

Expected: no matches. Historical design/plan documents may still contain those terms and are intentionally excluded.

Run:

```bash
rg -n "equal_weight_consensus|single_source_fallback|forecast_sources_unavailable|MUFG" \
  python/backend python/tests README.md
```

Expected: matches in schemas, errors, service, route, tests, and README.

- [ ] **Step 3: Run the complete automated suite**

Run:

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests -v
```

Expected: all tests PASS with no network access. The exact count must be at least the pre-Phase-9 baseline of 204 plus the new MUFG, institution-service, consensus, fallback, and downstream provenance cases.

- [ ] **Step 4: Start the local API and perform one live-source smoke test**

Start:

```bash
.venv/bin/python -m uvicorn backend.main:app --app-dir python --host 127.0.0.1 --port 8000
```

In another terminal, use `2026-11-15`; relative to the plan date it is in the future, within 365 days, and inside the currently observed ING/MUFG forecast horizons:

```bash
curl --get 'http://127.0.0.1:8000/api/v1/forecasts/usd-cny/maturity-estimate' \
  --data-urlencode 'maturity_date=2026-11-15'
```

Expected: HTTP 200 with either `equal_weight_consensus` and two sources or an explicitly traceable `single_source_fallback`. If the current public page structure has legitimately changed, preserve the automated test evidence, record the failing source and stable public error, and fix only the corresponding parser under the same validation rules before claiming completion.

- [ ] **Step 5: Review the final diff and commit documentation**

Run:

```bash
git diff --check
git status --short
git diff --stat HEAD~6..HEAD
```

Expected: `git diff --check` has no output; status contains only the intended README change before committing.

```bash
git add README.md
git commit -m "docs: explain consensus forecast testing"
```

- [ ] **Step 6: Record final repository evidence**

Run:

```bash
git status --short --branch
git log --oneline -8
```

Expected: clean worktree on the implementation branch, with focused commits for primitives, MUFG, cache isolation, institution service, consensus, API wiring, and docs. Do not push or merge unless the user separately asks for publication.
