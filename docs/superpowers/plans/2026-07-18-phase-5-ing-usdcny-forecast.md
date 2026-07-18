# Phase 5 ING USD/CNY Maturity Forecast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only endpoint that turns ING's public quarterly USD/CNY forecasts into a traceable expected spot for any supported maturity date within the next 365 natural days.

**Architecture:** A provider-specific ING adapter parses only the fixed official FX table into a validated institutional snapshot. A pure matcher handles direct dates and natural-day interpolation, while an atomic JSON cache and orchestration service apply freshness, network fallback, conditional FRED anchoring, and stable response/error contracts.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, httpx, Python `html.parser`/`json` standard libraries, pytest, FastAPI `TestClient`.

## Global Constraints

- Currency pair is exactly `USD/CNY`, quoted as `CNY per 1 USD`.
- The only institutional source in this phase is ING's public fixed page: `https://think.ing.com/forecasts/`.
- The response must say `source_count: 1`, `aggregation_status: single_source_trial`, and `is_consensus_forecast: false`.
- A user maturity must satisfy `valuation_date < maturity_date <= valuation_date + 365 days`.
- Quarter labels map to quarter-end natural dates: `1QyyF` to March 31, `2QyyF` to June 30, `3QyyF` to September 30, and `4QyyF` to December 31.
- Exact ING dates use the original point; dates between anchors use full-precision natural-day linear interpolation.
- FRED is fetched only when maturity is before the first future ING point; direct ING matches and interpolation between two ING points must not depend on FRED.
- FRED anchors use their actual observation date and retain Phase 4's maximum 14-day market-data age.
- No extrapolation is allowed after the last available ING point, even when maturity is within 365 days.
- ING's source update date may be no more than 45 natural days old.
- Normal cache reuse is 24 hours; network-only stale fallback is allowed through 7 days.
- A downloaded but structurally invalid ING page must fail visibly and must not use a cache older than 24 hours to hide the format change.
- Automated tests never call the live ING or FRED websites.
- No probability endpoint, multi-institution weighting, paid forward curve, database, background scheduler, PDF parser, or LLM extraction is included.

---

### Task 1: Parse and Fetch the Official ING FX Forecast

**Files:**
- Create: `python/backend/forecast/__init__.py`
- Create: `python/backend/forecast/types.py`
- Create: `python/backend/forecast/errors.py`
- Create: `python/backend/forecast/ing.py`
- Create: `python/tests/backend/test_ing_forecast.py`

**Interfaces:**
- Consumes: fixed ING HTML text, an aware UTC retrieval timestamp, and an injected `httpx.Client`.
- Produces: `ForecastPoint`, `InstitutionForecastSnapshot`, `ForecastProvider`, `parse_quarter_label`, `parse_ing_forecast_html`, `IngForecastProvider.fetch(retrieved_at_utc)`, `ForecastFetchError`, and stable forecast errors.

- [ ] **Step 1: Write failing parser and provider tests**

Create `python/tests/backend/test_ing_forecast.py`:

```python
from datetime import date, datetime, timezone

import httpx
import pytest

from backend.forecast.errors import ForecastFetchError, ForecastSourceInvalidError
from backend.forecast.ing import (
    ING_FORECAST_URL,
    IngForecastProvider,
    parse_ing_forecast_html,
    parse_quarter_label,
)


RETRIEVED_AT = datetime(2026, 7, 18, 10, tzinfo=timezone.utc)


def ing_html(*, updated: str = "16 July", pair: str = "USD/CNY") -> str:
    return f"""
    <div id="growth-gdp">
      <h2>Growth (GDP)</h2><p>Last updated: 1 July</p>
      <table><thead><tr><th>Asia</th><th></th><th>3Q26F</th></tr></thead>
      <tbody><tr><td>China</td><td>{pair}</td><td>99</td></tr></tbody></table>
    </div>
    <div id="fx">
      <h2>FX</h2><p>Last updated: {updated}</p>
      <table>
        <thead><tr><th>Asia (eop)</th><th></th><th>3Q26F</th><th>4Q26F</th><th>1Q27F</th></tr></thead>
        <tbody><tr><td>China</td><td>{pair}</td><td>6.74</td><td>6.70</td><td>6.68</td></tr></tbody>
      </table>
    </div>
    """


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("1Q27F", date(2027, 3, 31)),
        ("2Q27F", date(2027, 6, 30)),
        ("3Q27F", date(2027, 9, 30)),
        ("4Q27F", date(2027, 12, 31)),
    ],
)
def test_parse_quarter_label_uses_natural_quarter_end(
    label: str,
    expected: date,
) -> None:
    assert parse_quarter_label(label) == expected


def test_parser_reads_only_fx_usd_cny_and_resolves_update_year() -> None:
    snapshot = parse_ing_forecast_html(ing_html(), RETRIEVED_AT)

    assert snapshot.institution == "ING"
    assert snapshot.currency_pair == "USD/CNY"
    assert snapshot.source_url == ING_FORECAST_URL
    assert snapshot.source_updated_date == date(2026, 7, 16)
    assert [(item.date, item.spot) for item in snapshot.points] == [
        (date(2026, 9, 30), 6.74),
        (date(2026, 12, 31), 6.70),
        (date(2027, 3, 31), 6.68),
    ]


def test_parser_resolves_december_update_to_previous_year_in_january() -> None:
    retrieved = datetime(2026, 1, 5, tzinfo=timezone.utc)

    snapshot = parse_ing_forecast_html(
        ing_html(updated="20 December"),
        retrieved,
    )

    assert snapshot.source_updated_date == date(2025, 12, 20)


@pytest.mark.parametrize(
    "html_text",
    [
        "<div id='growth-gdp'><p>Last updated: 16 July</p></div>",
        ing_html(pair="CNY/USD"),
        ing_html().replace("6.74", "0"),
        ing_html().replace("3Q26F", "Q3-2026"),
        ing_html().replace("<td>6.70</td>", "<td>not-a-number</td>"),
    ],
)
def test_parser_rejects_missing_or_invalid_fx_content(html_text: str) -> None:
    with pytest.raises(ForecastSourceInvalidError):
        parse_ing_forecast_html(html_text, RETRIEVED_AT)


def test_provider_requests_only_the_fixed_official_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == ING_FORECAST_URL
        assert "fx-hedging-platform" in request.headers["User-Agent"]
        return httpx.Response(200, text=ing_html())

    provider = IngForecastProvider(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    snapshot = provider.fetch(RETRIEVED_AT)

    assert snapshot.points[0].spot == 6.74


@pytest.mark.parametrize("status", [404, 429, 503])
def test_provider_maps_http_failures_to_fetch_error(status: int) -> None:
    provider = IngForecastProvider(
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, text="unavailable")
            )
        )
    )

    with pytest.raises(ForecastFetchError):
        provider.fetch(RETRIEVED_AT)
```

- [ ] **Step 2: Run the test and verify the forecast package is missing**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_ing_forecast.py -v
```

Expected: collection fails because `backend.forecast` does not exist.

- [ ] **Step 3: Define forecast types and exceptions**

Create an empty `python/backend/forecast/__init__.py`.

Create `python/backend/forecast/types.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class ForecastPoint:
    date: date
    spot: float


@dataclass(frozen=True)
class InstitutionForecastSnapshot:
    institution: str
    currency_pair: str
    source_url: str
    source_updated_date: date
    fetched_at_utc: datetime
    points: tuple[ForecastPoint, ...]


@dataclass(frozen=True)
class ForecastAnchor:
    source: str
    date: date
    spot: float


@dataclass(frozen=True)
class ForecastMatch:
    expected_spot: float
    method: str
    is_system_estimate: bool
    day_weight: float | None
    anchors: tuple[ForecastAnchor, ...]


class ForecastProvider(Protocol):
    def fetch(
        self,
        retrieved_at_utc: datetime,
    ) -> InstitutionForecastSnapshot: ...
```

Create `python/backend/forecast/errors.py`:

```python
class ForecastError(Exception):
    code = "forecast_error"
    message = "到期汇率预测失败"
    status_code = 503


class ForecastFetchError(Exception):
    pass


class ForecastAnchorRequiredError(Exception):
    pass


class ForecastMaturityInvalidError(ForecastError):
    code = "forecast_maturity_invalid"
    message = "到期日必须在未来1天至365天之内"
    status_code = 422


class ForecastHorizonInsufficientError(ForecastError):
    code = "forecast_horizon_insufficient"
    message = "ING预测期限不足，无法覆盖该到期日"
    status_code = 503


class ForecastSourceUnavailableError(ForecastError):
    code = "forecast_source_unavailable"
    message = "ING预测数据暂时不可用，请稍后重试"
    status_code = 503


class ForecastSourceInvalidError(ForecastError):
    code = "forecast_source_invalid"
    message = "ING预测页面格式异常，请稍后重试"
    status_code = 502


class ForecastSourceStaleError(ForecastError):
    code = "forecast_source_stale"
    message = "ING预测已超过45天未更新"
    status_code = 503
```

- [ ] **Step 4: Implement strict ING HTML parsing and HTTP fetching**

Create `python/backend/forecast/ing.py`:

```python
import re
from datetime import date, datetime
from html.parser import HTMLParser
from math import isfinite

import httpx

from backend.forecast.errors import ForecastFetchError, ForecastSourceInvalidError
from backend.forecast.types import ForecastPoint, InstitutionForecastSnapshot


ING_FORECAST_URL = "https://think.ing.com/forecasts/"
REQUEST_TIMEOUT_SECONDS = 10.0
USER_AGENT = "fx-hedging-platform/0.1 market-data-client"
QUARTER_PATTERN = re.compile(r"([1-4])Q(\d{2})F")
UPDATED_PATTERN = re.compile(r"Last updated:\s*(\d{1,2})\s+([A-Za-z]+)")
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


class _IngFxParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_fx = False
        self.fx_div_depth = 0
        self.in_thead = False
        self.in_tbody = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.current_row: list[str] = []
        self.current_headers: tuple[str, ...] = ()
        self.fx_text_parts: list[str] = []
        self.candidates: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "div":
            if self.in_fx:
                self.fx_div_depth += 1
            elif attributes.get("id") == "fx":
                self.in_fx = True
                self.fx_div_depth = 1
        if not self.in_fx:
            return
        if tag == "thead":
            self.in_thead = True
        elif tag == "tbody":
            self.in_tbody = True
        elif tag == "tr":
            self.current_row = []
        elif tag in {"th", "td"}:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_fx:
            self.fx_text_parts.append(data)
        if self.in_fx and self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.in_fx:
            return
        if tag in {"th", "td"} and self.in_cell:
            self.current_row.append(" ".join(self.cell_parts).strip())
            self.in_cell = False
            self.cell_parts = []
        elif tag == "tr":
            row = tuple(self.current_row)
            if self.in_thead and row:
                self.current_headers = row
            elif self.in_tbody and len(row) >= 2:
                if row[0] == "China" and row[1] == "USD/CNY":
                    self.candidates.append((self.current_headers, row))
            self.current_row = []
        elif tag == "thead":
            self.in_thead = False
        elif tag == "tbody":
            self.in_tbody = False
        if tag == "div":
            self.fx_div_depth -= 1
            if self.fx_div_depth == 0:
                self.in_fx = False


def parse_quarter_label(label: str) -> date:
    match = QUARTER_PATTERN.fullmatch(label.strip())
    if match is None:
        raise ForecastSourceInvalidError()
    quarter = int(match.group(1))
    year = 2000 + int(match.group(2))
    month_day = {
        1: (3, 31),
        2: (6, 30),
        3: (9, 30),
        4: (12, 31),
    }
    month, day = month_day[quarter]
    return date(year, month, day)


def _resolve_updated_date(text: str, retrieved_on: date) -> date:
    match = UPDATED_PATTERN.search(text)
    if match is None:
        raise ForecastSourceInvalidError()
    day = int(match.group(1))
    month = MONTHS.get(match.group(2).lower())
    if month is None:
        raise ForecastSourceInvalidError()
    candidates: list[date] = []
    for year in (retrieved_on.year, retrieved_on.year - 1):
        try:
            candidate = date(year, month, day)
        except ValueError as exc:
            raise ForecastSourceInvalidError() from exc
        if candidate <= retrieved_on:
            candidates.append(candidate)
    if not candidates:
        raise ForecastSourceInvalidError()
    return max(candidates)


def parse_ing_forecast_html(
    html_text: str,
    retrieved_at_utc: datetime,
) -> InstitutionForecastSnapshot:
    if retrieved_at_utc.tzinfo is None:
        raise ForecastSourceInvalidError()
    parser = _IngFxParser()
    parser.feed(html_text)
    parser.close()
    if len(parser.candidates) != 1:
        raise ForecastSourceInvalidError()

    headers, row = parser.candidates[0]
    if len(headers) != len(row) or len(headers) < 4:
        raise ForecastSourceInvalidError()
    points: list[ForecastPoint] = []
    for label, raw_spot in zip(headers[2:], row[2:]):
        point_date = parse_quarter_label(label)
        try:
            spot = float(raw_spot)
        except ValueError as exc:
            raise ForecastSourceInvalidError() from exc
        if not isfinite(spot) or spot <= 0:
            raise ForecastSourceInvalidError()
        points.append(ForecastPoint(point_date, spot))

    point_dates = [item.date for item in points]
    if point_dates != sorted(set(point_dates)):
        raise ForecastSourceInvalidError()
    future_count = sum(
        item.date > retrieved_at_utc.date()
        for item in points
    )
    if future_count < 2:
        raise ForecastSourceInvalidError()
    updated_date = _resolve_updated_date(
        " ".join(parser.fx_text_parts),
        retrieved_at_utc.date(),
    )
    return InstitutionForecastSnapshot(
        institution="ING",
        currency_pair="USD/CNY",
        source_url=ING_FORECAST_URL,
        source_updated_date=updated_date,
        fetched_at_utc=retrieved_at_utc,
        points=tuple(points),
    )


class IngForecastProvider:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client or httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    def fetch(
        self,
        retrieved_at_utc: datetime,
    ) -> InstitutionForecastSnapshot:
        try:
            response = self._http_client.get(
                ING_FORECAST_URL,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ForecastFetchError() from exc
        return parse_ing_forecast_html(response.text, retrieved_at_utc)
```

- [ ] **Step 5: Run the ING parser/provider tests**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_ing_forecast.py -v
```

Expected: all ING parser and HTTP tests pass without a live network call.

- [ ] **Step 6: Commit the ING adapter**

```bash
git add python/backend/forecast python/tests/backend/test_ing_forecast.py
git commit -m "feat: read ING USD CNY forecasts"
```

---

### Task 2: Match an Arbitrary Supported Maturity Date

**Files:**
- Create: `python/backend/forecast/matcher.py`
- Create: `python/tests/backend/test_forecast_matcher.py`

**Interfaces:**
- Consumes: valuation date, maturity date, ordered ING `ForecastPoint` values, and an optional FRED `ForecastAnchor`.
- Produces: `validate_maturity_date(valuation_date, maturity_date) -> None` and `match_maturity_forecast(...) -> ForecastMatch` with `direct` or `interpolated` method and stable maturity/horizon errors.

- [ ] **Step 1: Write failing matching tests**

Create `python/tests/backend/test_forecast_matcher.py`:

```python
from datetime import date, timedelta

import pytest

from backend.forecast.errors import (
    ForecastAnchorRequiredError,
    ForecastHorizonInsufficientError,
    ForecastMaturityInvalidError,
)
from backend.forecast.matcher import match_maturity_forecast
from backend.forecast.types import ForecastAnchor, ForecastPoint


VALUATION_DATE = date(2026, 7, 18)
POINTS = (
    ForecastPoint(date(2026, 9, 30), 6.74),
    ForecastPoint(date(2026, 12, 31), 6.70),
    ForecastPoint(date(2027, 3, 31), 6.68),
)


def test_exact_ing_date_returns_direct_original_point() -> None:
    result = match_maturity_forecast(
        valuation_date=VALUATION_DATE,
        maturity_date=date(2026, 12, 31),
        ing_points=POINTS,
    )

    assert result.expected_spot == 6.70
    assert result.method == "direct"
    assert result.is_system_estimate is False
    assert result.day_weight is None
    assert result.anchors == (
        ForecastAnchor("ING", date(2026, 12, 31), 6.70),
    )


def test_between_ing_points_interpolates_by_natural_days() -> None:
    result = match_maturity_forecast(
        valuation_date=VALUATION_DATE,
        maturity_date=date(2026, 11, 15),
        ing_points=POINTS,
    )

    assert result.day_weight == pytest.approx(0.5)
    assert result.expected_spot == pytest.approx(6.72)
    assert [item.source for item in result.anchors] == ["ING", "ING"]


def test_before_first_ing_point_requires_and_uses_actual_fred_anchor() -> None:
    with pytest.raises(ForecastAnchorRequiredError):
        match_maturity_forecast(
            valuation_date=VALUATION_DATE,
            maturity_date=date(2026, 8, 15),
            ing_points=POINTS,
        )

    result = match_maturity_forecast(
        valuation_date=VALUATION_DATE,
        maturity_date=date(2026, 8, 15),
        ing_points=POINTS,
        fred_anchor=ForecastAnchor("FRED", date(2026, 7, 10), 6.7766),
    )

    expected_weight = 36 / 82
    assert result.day_weight == pytest.approx(expected_weight)
    assert result.expected_spot == pytest.approx(
        6.7766 + expected_weight * (6.74 - 6.7766)
    )
    assert result.anchors[0].date == date(2026, 7, 10)


@pytest.mark.parametrize(
    "maturity_date",
    [
        VALUATION_DATE,
        VALUATION_DATE - timedelta(days=1),
        VALUATION_DATE + timedelta(days=366),
    ],
)
def test_maturity_must_be_in_the_next_365_days(maturity_date: date) -> None:
    with pytest.raises(ForecastMaturityInvalidError):
        match_maturity_forecast(
            valuation_date=VALUATION_DATE,
            maturity_date=maturity_date,
            ing_points=POINTS,
        )


def test_matcher_never_extrapolates_after_last_ing_point() -> None:
    with pytest.raises(ForecastHorizonInsufficientError):
        match_maturity_forecast(
            valuation_date=VALUATION_DATE,
            maturity_date=date(2027, 4, 1),
            ing_points=POINTS,
        )
```

- [ ] **Step 2: Run the test and verify the matcher is missing**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_forecast_matcher.py -v
```

Expected: collection fails for missing `backend.forecast.matcher`.

- [ ] **Step 3: Implement direct matching and interpolation**

Create `python/backend/forecast/matcher.py`:

```python
from datetime import date, timedelta
from math import isfinite
from typing import Sequence

from backend.forecast.errors import (
    ForecastAnchorRequiredError,
    ForecastHorizonInsufficientError,
    ForecastMaturityInvalidError,
    ForecastSourceInvalidError,
)
from backend.forecast.types import (
    ForecastAnchor,
    ForecastMatch,
    ForecastPoint,
)


MAX_MATURITY_DAYS = 365


def validate_maturity_date(
    valuation_date: date,
    maturity_date: date,
) -> None:
    if not (
        valuation_date < maturity_date
        <= valuation_date + timedelta(days=MAX_MATURITY_DAYS)
    ):
        raise ForecastMaturityInvalidError()


def _interpolate(
    maturity_date: date,
    before: ForecastAnchor,
    after: ForecastAnchor,
) -> ForecastMatch:
    total_days = (after.date - before.date).days
    elapsed_days = (maturity_date - before.date).days
    if total_days <= 0 or elapsed_days <= 0 or elapsed_days >= total_days:
        raise ForecastSourceInvalidError()
    weight = elapsed_days / total_days
    expected_spot = before.spot + weight * (after.spot - before.spot)
    if not isfinite(expected_spot) or expected_spot <= 0:
        raise ForecastSourceInvalidError()
    return ForecastMatch(
        expected_spot=expected_spot,
        method="interpolated",
        is_system_estimate=True,
        day_weight=weight,
        anchors=(before, after),
    )


def match_maturity_forecast(
    *,
    valuation_date: date,
    maturity_date: date,
    ing_points: Sequence[ForecastPoint],
    fred_anchor: ForecastAnchor | None = None,
) -> ForecastMatch:
    validate_maturity_date(valuation_date, maturity_date)
    future_points = tuple(
        item for item in ing_points if item.date > valuation_date
    )
    if not future_points or maturity_date > future_points[-1].date:
        raise ForecastHorizonInsufficientError()

    for point in future_points:
        if point.date == maturity_date:
            anchor = ForecastAnchor("ING", point.date, point.spot)
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
            ForecastAnchor("ING", first.date, first.spot),
        )

    for before, after in zip(future_points, future_points[1:]):
        if before.date < maturity_date < after.date:
            return _interpolate(
                maturity_date,
                ForecastAnchor("ING", before.date, before.spot),
                ForecastAnchor("ING", after.date, after.spot),
            )
    raise ForecastHorizonInsufficientError()
```

- [ ] **Step 4: Run the matcher tests**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_forecast_matcher.py -v
```

Expected: all exact-date, interpolation, FRED-anchor, maturity, and no-extrapolation tests pass.

- [ ] **Step 5: Commit the matcher**

```bash
git add python/backend/forecast/matcher.py python/tests/backend/test_forecast_matcher.py
git commit -m "feat: match forecast maturity dates"
```

---
### Task 3: Persist a Validated ING Forecast Snapshot

**Files:**
- Create: `python/backend/forecast/cache.py`
- Create: `python/tests/backend/test_forecast_cache.py`

**Interfaces:**
- Consumes: a cache `Path` and Task 1's `InstitutionForecastSnapshot`.
- Produces: `JsonForecastCache.load() -> InstitutionForecastSnapshot | None`, `JsonForecastCache.save(snapshot) -> None`, and `default_forecast_cache_path() -> Path`.

- [ ] **Step 1: Write failing cache tests**

Create `python/tests/backend/test_forecast_cache.py`:

```python
import json
from datetime import date, datetime, timezone
from pathlib import Path

from backend.forecast.cache import JsonForecastCache
from backend.forecast.types import ForecastPoint, InstitutionForecastSnapshot


def snapshot() -> InstitutionForecastSnapshot:
    return InstitutionForecastSnapshot(
        institution="ING",
        currency_pair="USD/CNY",
        source_url="https://think.ing.com/forecasts/",
        source_updated_date=date(2026, 7, 16),
        fetched_at_utc=datetime(2026, 7, 18, 10, tzinfo=timezone.utc),
        points=(
            ForecastPoint(date(2026, 9, 30), 6.74),
            ForecastPoint(date(2026, 12, 31), 6.70),
        ),
    )


def test_forecast_cache_round_trips_snapshot(tmp_path: Path) -> None:
    cache = JsonForecastCache(tmp_path / "forecast.json")

    cache.save(snapshot())

    assert cache.load() == snapshot()


def test_missing_or_corrupt_forecast_cache_returns_none(tmp_path: Path) -> None:
    cache_path = tmp_path / "forecast.json"
    cache = JsonForecastCache(cache_path)
    assert cache.load() is None

    cache_path.write_text("not-json", encoding="utf-8")
    assert cache.load() is None


def test_structurally_untrusted_forecast_cache_returns_none(tmp_path: Path) -> None:
    cache_path = tmp_path / "forecast.json"
    cache = JsonForecastCache(cache_path)
    cache.save(snapshot())
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["currency_pair"] = "CNY/USD"
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    assert cache.load() is None


def test_forecast_cache_rejects_duplicate_or_nonpositive_points(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "forecast.json"
    cache = JsonForecastCache(cache_path)
    cache.save(snapshot())
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["points"][1] = payload["points"][0]
    payload["points"][1]["spot"] = -1
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    assert cache.load() is None


def test_forecast_cache_atomic_save_leaves_no_temp_file(tmp_path: Path) -> None:
    cache = JsonForecastCache(tmp_path / "forecast.json")

    cache.save(snapshot())

    assert [path.name for path in tmp_path.iterdir()] == ["forecast.json"]
```

- [ ] **Step 2: Run the test and verify the cache module is missing**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_forecast_cache.py -v
```

Expected: collection fails for missing `backend.forecast.cache`.

- [ ] **Step 3: Implement atomic validated JSON persistence**

Create `python/backend/forecast/cache.py`:

```python
import json
import os
import tempfile
from datetime import date, datetime
from math import isfinite
from pathlib import Path

from backend.forecast.ing import ING_FORECAST_URL
from backend.forecast.types import ForecastPoint, InstitutionForecastSnapshot


def default_forecast_cache_path() -> Path:
    python_root = Path(__file__).resolve().parents[2]
    return python_root / ".cache" / "market-data" / "ing-usdcny-forecast.json"


class JsonForecastCache:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> InstitutionForecastSnapshot | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            snapshot = InstitutionForecastSnapshot(
                institution=payload["institution"],
                currency_pair=payload["currency_pair"],
                source_url=payload["source_url"],
                source_updated_date=date.fromisoformat(
                    payload["source_updated_date"]
                ),
                fetched_at_utc=datetime.fromisoformat(
                    payload["fetched_at_utc"].replace("Z", "+00:00")
                ),
                points=tuple(
                    ForecastPoint(
                        date.fromisoformat(item["date"]),
                        item["spot"],
                    )
                    for item in payload["points"]
                ),
            )
            point_dates = [item.date for item in snapshot.points]
            if (
                snapshot.institution != "ING"
                or snapshot.currency_pair != "USD/CNY"
                or snapshot.source_url != ING_FORECAST_URL
                or snapshot.fetched_at_utc.tzinfo is None
                or snapshot.source_updated_date > snapshot.fetched_at_utc.date()
                or len(snapshot.points) < 2
                or point_dates != sorted(set(point_dates))
                or any(
                    not isfinite(item.spot) or item.spot <= 0
                    for item in snapshot.points
                )
            ):
                return None
            return snapshot
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def save(self, snapshot: InstitutionForecastSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "institution": snapshot.institution,
            "currency_pair": snapshot.currency_pair,
            "source_url": snapshot.source_url,
            "source_updated_date": snapshot.source_updated_date.isoformat(),
            "fetched_at_utc": snapshot.fetched_at_utc.isoformat().replace(
                "+00:00", "Z"
            ),
            "points": [
                {"date": item.date.isoformat(), "spot": item.spot}
                for item in snapshot.points
            ],
        }
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                delete=False,
            ) as temp_file:
                temp_name = temp_file.name
                json.dump(payload, temp_file, ensure_ascii=False)
            os.replace(temp_name, self.path)
        finally:
            if temp_name is not None and Path(temp_name).exists():
                Path(temp_name).unlink()
```

The existing `.gitignore` already ignores `/python/.cache/`; do not add a second ignore rule.

- [ ] **Step 4: Run the forecast cache tests**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_forecast_cache.py -v
```

Expected: all forecast cache tests pass and only the final JSON exists in each pytest temporary directory.

- [ ] **Step 5: Commit the forecast cache**

```bash
git add python/backend/forecast/cache.py python/tests/backend/test_forecast_cache.py
git commit -m "feat: cache ING forecast snapshots"
```

---

### Task 4: Orchestrate ING Freshness, Fallback, Conditional FRED, and Output

**Files:**
- Create: `python/backend/forecast/schemas.py`
- Create: `python/backend/forecast/service.py`
- Create: `python/tests/backend/test_maturity_forecast_service.py`

**Interfaces:**
- Consumes: `ForecastProvider`, `JsonForecastCache`, Task 2's matcher, an injected market-history service, and an injected UTC clock.
- Produces: `MaturityForecastService.get_estimate(maturity_date) -> MaturityForecastResponse` and approved Pydantic response types.

- [ ] **Step 1: Write failing service behavior tests**

Create `python/tests/backend/test_maturity_forecast_service.py`:

```python
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.forecast.cache import JsonForecastCache
from backend.forecast.errors import (
    ForecastFetchError,
    ForecastMaturityInvalidError,
    ForecastSourceInvalidError,
    ForecastSourceStaleError,
    ForecastSourceUnavailableError,
)
from backend.forecast.service import MaturityForecastService
from backend.forecast.types import ForecastPoint, InstitutionForecastSnapshot


NOW = datetime(2026, 7, 18, 10, tzinfo=timezone.utc)


def snapshot(
    *,
    fetched_at: datetime = NOW,
    updated_on: date = date(2026, 7, 16),
) -> InstitutionForecastSnapshot:
    return InstitutionForecastSnapshot(
        institution="ING",
        currency_pair="USD/CNY",
        source_url="https://think.ing.com/forecasts/",
        source_updated_date=updated_on,
        fetched_at_utc=fetched_at,
        points=(
            ForecastPoint(date(2026, 9, 30), 6.74),
            ForecastPoint(date(2026, 12, 31), 6.70),
            ForecastPoint(date(2027, 3, 31), 6.68),
        ),
    )


class FakeProvider:
    def __init__(
        self,
        result: InstitutionForecastSnapshot | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or snapshot()
        self.error = error
        self.calls = 0

    def fetch(self, retrieved_at_utc: datetime) -> InstitutionForecastSnapshot:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class FakeMarketService:
    def __init__(self) -> None:
        self.calls = 0

    def get_summary(self):
        self.calls += 1
        return SimpleNamespace(
            market_reference=SimpleNamespace(
                spot=6.7766,
                observation_date=date(2026, 7, 10),
            )
        )


def service(
    tmp_path: Path,
    provider: FakeProvider,
    market: FakeMarketService,
) -> MaturityForecastService:
    return MaturityForecastService(
        provider=provider,
        cache=JsonForecastCache(tmp_path / "forecast.json"),
        market_history_service=market,
        now_utc=lambda: NOW,
    )


def test_direct_ing_match_does_not_call_fred(tmp_path: Path) -> None:
    provider = FakeProvider()
    market = FakeMarketService()

    result = service(tmp_path, provider, market).get_estimate(
        date(2026, 12, 31)
    )

    assert provider.calls == 1
    assert market.calls == 0
    assert result.expected_maturity_spot == 6.70
    assert result.matching.method == "direct"
    assert result.source_count == 1
    assert result.aggregation_status == "single_source_trial"
    assert result.is_consensus_forecast is False
    assert result.sources[0].cache_status == "live_fetch"


def test_between_ing_points_does_not_call_fred(tmp_path: Path) -> None:
    market = FakeMarketService()

    result = service(tmp_path, FakeProvider(), market).get_estimate(
        date(2026, 11, 15)
    )

    assert market.calls == 0
    assert result.expected_maturity_spot == pytest.approx(6.72)
    assert [item.source for item in result.matching.anchors] == ["ING", "ING"]


def test_before_first_ing_point_calls_fred_and_returns_actual_anchor(
    tmp_path: Path,
) -> None:
    market = FakeMarketService()

    result = service(tmp_path, FakeProvider(), market).get_estimate(
        date(2026, 8, 15)
    )

    assert market.calls == 1
    assert result.matching.anchors[0].source == "FRED"
    assert result.matching.anchors[0].date == date(2026, 7, 10)


def test_daily_cache_avoids_ing_and_still_avoids_unneeded_fred(
    tmp_path: Path,
) -> None:
    cache = JsonForecastCache(tmp_path / "forecast.json")
    cache.save(snapshot(fetched_at=NOW - timedelta(hours=23)))
    provider = FakeProvider(error=ForecastFetchError())
    market = FakeMarketService()

    result = service(tmp_path, provider, market).get_estimate(
        date(2026, 11, 15)
    )

    assert provider.calls == 0
    assert market.calls == 0
    assert result.sources[0].cache_status == "daily_cache"


def test_network_failure_uses_cache_through_seven_days(tmp_path: Path) -> None:
    cache = JsonForecastCache(tmp_path / "forecast.json")
    cache.save(snapshot(fetched_at=NOW - timedelta(days=6)))

    result = service(
        tmp_path,
        FakeProvider(error=ForecastFetchError()),
        FakeMarketService(),
    ).get_estimate(date(2026, 11, 15))

    assert result.sources[0].cache_status == "stale_fallback"
    assert result.sources[0].is_stale is True


def test_network_failure_rejects_cache_older_than_seven_days(
    tmp_path: Path,
) -> None:
    cache = JsonForecastCache(tmp_path / "forecast.json")
    cache.save(snapshot(fetched_at=NOW - timedelta(days=8)))

    with pytest.raises(ForecastSourceUnavailableError):
        service(
            tmp_path,
            FakeProvider(error=ForecastFetchError()),
            FakeMarketService(),
        ).get_estimate(date(2026, 11, 15))


def test_future_dated_cache_is_ignored_and_refetched(tmp_path: Path) -> None:
    cache = JsonForecastCache(tmp_path / "forecast.json")
    cache.save(snapshot(fetched_at=NOW + timedelta(hours=1)))
    provider = FakeProvider()

    result = service(
        tmp_path,
        provider,
        FakeMarketService(),
    ).get_estimate(date(2026, 11, 15))

    assert provider.calls == 1
    assert result.sources[0].cache_status == "live_fetch"


def test_invalid_page_does_not_hide_behind_old_cache(tmp_path: Path) -> None:
    cache = JsonForecastCache(tmp_path / "forecast.json")
    cache.save(snapshot(fetched_at=NOW - timedelta(days=2)))

    with pytest.raises(ForecastSourceInvalidError):
        service(
            tmp_path,
            FakeProvider(error=ForecastSourceInvalidError()),
            FakeMarketService(),
        ).get_estimate(date(2026, 11, 15))


def test_invalid_maturity_does_not_fetch_external_sources(tmp_path: Path) -> None:
    provider = FakeProvider()
    market = FakeMarketService()

    with pytest.raises(ForecastMaturityInvalidError):
        service(tmp_path, provider, market).get_estimate(NOW.date())

    assert provider.calls == 0
    assert market.calls == 0


def test_source_update_older_than_45_days_is_rejected(tmp_path: Path) -> None:
    provider = FakeProvider(
        result=snapshot(updated_on=NOW.date() - timedelta(days=46))
    )

    with pytest.raises(ForecastSourceStaleError):
        service(tmp_path, provider, FakeMarketService()).get_estimate(
            date(2026, 11, 15)
        )
```

- [ ] **Step 2: Run the test and verify the service module is missing**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_maturity_forecast_service.py -v
```

Expected: collection fails for missing `backend.forecast.service`.

- [ ] **Step 3: Define response schemas**

Create `python/backend/forecast/schemas.py`:

```python
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


CacheStatus = Literal["live_fetch", "daily_cache", "stale_fallback"]


class ForecastPointResponse(BaseModel):
    date: date
    spot: float


class ForecastAnchorResponse(BaseModel):
    source: Literal["ING", "FRED"]
    date: date
    spot: float


class ForecastMatchingResponse(BaseModel):
    method: Literal["direct", "interpolated"]
    is_system_estimate: bool
    day_weight: float | None
    anchors: list[ForecastAnchorResponse]


class InstitutionForecastSourceResponse(BaseModel):
    institution: Literal["ING"] = "ING"
    source_updated_date: date
    source_url: str
    forecast_points: list[ForecastPointResponse]
    cache_status: CacheStatus
    fetched_at_utc: datetime
    cache_age_hours: float
    is_stale: bool


class MaturityForecastResponse(BaseModel):
    status: Literal["available"] = "available"
    currency_pair: Literal["USD/CNY"] = "USD/CNY"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    valuation_date: date
    maturity_date: date
    expected_maturity_spot: float
    matching: ForecastMatchingResponse
    source_count: Literal[1] = 1
    aggregation_status: Literal["single_source_trial"] = "single_source_trial"
    is_consensus_forecast: Literal[False] = False
    sources: list[InstitutionForecastSourceResponse]
    limitations: list[str]
```

- [ ] **Step 4: Implement cache/fetch orchestration and conditional FRED**

Create `python/backend/forecast/service.py`:

```python
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from backend.forecast.cache import JsonForecastCache
from backend.forecast.errors import (
    ForecastAnchorRequiredError,
    ForecastFetchError,
    ForecastSourceInvalidError,
    ForecastSourceStaleError,
    ForecastSourceUnavailableError,
)
from backend.forecast.matcher import (
    match_maturity_forecast,
    validate_maturity_date,
)
from backend.forecast.schemas import (
    ForecastAnchorResponse,
    ForecastMatchingResponse,
    ForecastPointResponse,
    InstitutionForecastSourceResponse,
    MaturityForecastResponse,
)
from backend.forecast.types import (
    ForecastAnchor,
    ForecastProvider,
    InstitutionForecastSnapshot,
)


NORMAL_CACHE_TTL = timedelta(hours=24)
FALLBACK_CACHE_TTL = timedelta(days=7)
MAX_SOURCE_AGE_DAYS = 45
LIMITATIONS = [
    "这是单一机构试验，不是多机构共识预测。",
    "插值结果是系统估算，不是ING对当天的直接预测。",
]


class MarketHistoryLookup(Protocol):
    def get_summary(self): ...


class MaturityForecastService:
    def __init__(
        self,
        *,
        provider: ForecastProvider,
        cache: JsonForecastCache,
        market_history_service: MarketHistoryLookup,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._market_history_service = market_history_service
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
        now = self._now_utc()
        validate_maturity_date(now.date(), maturity_date)
        snapshot, cache_status = self._get_snapshot(now)
        source_age_days = (now.date() - snapshot.source_updated_date).days
        if source_age_days < 0:
            raise ForecastSourceInvalidError()
        if source_age_days > MAX_SOURCE_AGE_DAYS:
            raise ForecastSourceStaleError()
        if cache_status == "live_fetch":
            self._cache.save(snapshot)

        try:
            matched = match_maturity_forecast(
                valuation_date=now.date(),
                maturity_date=maturity_date,
                ing_points=snapshot.points,
            )
        except ForecastAnchorRequiredError:
            market_summary = self._market_history_service.get_summary()
            reference = market_summary.market_reference
            matched = match_maturity_forecast(
                valuation_date=now.date(),
                maturity_date=maturity_date,
                ing_points=snapshot.points,
                fred_anchor=ForecastAnchor(
                    source="FRED",
                    date=reference.observation_date,
                    spot=reference.spot,
                ),
            )

        cache_age_hours = max(
            0.0,
            (now - snapshot.fetched_at_utc).total_seconds() / 3600,
        )
        return MaturityForecastResponse(
            valuation_date=now.date(),
            maturity_date=maturity_date,
            expected_maturity_spot=matched.expected_spot,
            matching=ForecastMatchingResponse(
                method=matched.method,
                is_system_estimate=matched.is_system_estimate,
                day_weight=matched.day_weight,
                anchors=[
                    ForecastAnchorResponse(
                        source=item.source,
                        date=item.date,
                        spot=item.spot,
                    )
                    for item in matched.anchors
                ],
            ),
            sources=[
                InstitutionForecastSourceResponse(
                    source_updated_date=snapshot.source_updated_date,
                    source_url=snapshot.source_url,
                    forecast_points=[
                        ForecastPointResponse(date=item.date, spot=item.spot)
                        for item in snapshot.points
                    ],
                    cache_status=cache_status,
                    fetched_at_utc=snapshot.fetched_at_utc,
                    cache_age_hours=cache_age_hours,
                    is_stale=cache_status == "stale_fallback",
                )
            ],
            limitations=LIMITATIONS,
        )

    def _get_snapshot(
        self,
        now: datetime,
    ) -> tuple[InstitutionForecastSnapshot, str]:
        cached = self._cache.load()
        cache_age = None if cached is None else now - cached.fetched_at_utc
        if (
            cached is not None
            and cache_age is not None
            and timedelta(0) <= cache_age <= NORMAL_CACHE_TTL
        ):
            return cached, "daily_cache"
        try:
            return self._provider.fetch(now), "live_fetch"
        except ForecastFetchError as exc:
            if (
                cached is None
                or cache_age is None
                or cache_age < timedelta(0)
                or cache_age > FALLBACK_CACHE_TTL
            ):
                raise ForecastSourceUnavailableError() from exc
            return cached, "stale_fallback"
```

- [ ] **Step 5: Run service tests**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_maturity_forecast_service.py -v
```

Expected: direct, ING interpolation, conditional FRED, cache, fallback, and stale-source tests all pass.

- [ ] **Step 6: Commit the forecast service**

```bash
git add python/backend/forecast/schemas.py python/backend/forecast/service.py python/tests/backend/test_maturity_forecast_service.py
git commit -m "feat: estimate USD CNY maturity spot"
```

---

### Task 5: Expose the Read-Only Maturity Forecast API

**Files:**
- Modify: `python/backend/errors.py`
- Modify: `python/backend/main.py`
- Create: `python/backend/routes/forecast.py`
- Create: `python/tests/backend/test_maturity_forecast_api.py`

**Interfaces:**
- Consumes: `MaturityForecastService`, `MaturityForecastResponse`, existing `get_market_history_service`, and `ForecastError`.
- Produces: `GET /api/v1/forecasts/usd-cny/maturity-estimate?maturity_date=YYYY-MM-DD`, a cached default service factory, and stable JSON errors.

- [ ] **Step 1: Write failing success and error endpoint tests**

Create `python/tests/backend/test_maturity_forecast_api.py`:

```python
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.forecast.errors import (
    ForecastHorizonInsufficientError,
    ForecastMaturityInvalidError,
    ForecastSourceInvalidError,
    ForecastSourceStaleError,
    ForecastSourceUnavailableError,
)
from backend.forecast.schemas import (
    ForecastAnchorResponse,
    ForecastMatchingResponse,
    ForecastPointResponse,
    InstitutionForecastSourceResponse,
    MaturityForecastResponse,
)
from backend.main import app
from backend.routes.forecast import get_maturity_forecast_service


class FakeService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
        if self.error is not None:
            raise self.error
        return MaturityForecastResponse(
            valuation_date=date(2026, 7, 18),
            maturity_date=maturity_date,
            expected_maturity_spot=6.72,
            matching=ForecastMatchingResponse(
                method="interpolated",
                is_system_estimate=True,
                day_weight=0.5,
                anchors=[
                    ForecastAnchorResponse(
                        source="ING",
                        date=date(2026, 9, 30),
                        spot=6.74,
                    ),
                    ForecastAnchorResponse(
                        source="ING",
                        date=date(2026, 12, 31),
                        spot=6.70,
                    ),
                ],
            ),
            sources=[
                InstitutionForecastSourceResponse(
                    source_updated_date=date(2026, 7, 16),
                    source_url="https://think.ing.com/forecasts/",
                    forecast_points=[
                        ForecastPointResponse(
                            date=date(2026, 9, 30),
                            spot=6.74,
                        ),
                        ForecastPointResponse(
                            date=date(2026, 12, 31),
                            spot=6.70,
                        ),
                    ],
                    cache_status="live_fetch",
                    fetched_at_utc=datetime(
                        2026, 7, 18, 10, tzinfo=timezone.utc
                    ),
                    cache_age_hours=0,
                    is_stale=False,
                )
            ],
            limitations=["单一机构试验"],
        )


def test_maturity_forecast_endpoint_returns_traceable_estimate() -> None:
    app.dependency_overrides[get_maturity_forecast_service] = lambda: FakeService()
    try:
        response = TestClient(app).get(
            "/api/v1/forecasts/usd-cny/maturity-estimate",
            params={"maturity_date": "2026-11-15"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["expected_maturity_spot"] == 6.72
    assert body["matching"]["method"] == "interpolated"
    assert body["source_count"] == 1
    assert body["aggregation_status"] == "single_source_trial"
    assert body["is_consensus_forecast"] is False
    assert body["sources"][0]["institution"] == "ING"
    assert body["sources"][0]["source_url"] == (
        "https://think.ing.com/forecasts/"
    )


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ForecastMaturityInvalidError(), 422, "forecast_maturity_invalid"),
        (
            ForecastHorizonInsufficientError(),
            503,
            "forecast_horizon_insufficient",
        ),
        (
            ForecastSourceUnavailableError(),
            503,
            "forecast_source_unavailable",
        ),
        (ForecastSourceInvalidError(), 502, "forecast_source_invalid"),
        (ForecastSourceStaleError(), 503, "forecast_source_stale"),
    ],
)
def test_maturity_forecast_endpoint_returns_stable_errors(
    error: Exception,
    status: int,
    code: str,
) -> None:
    app.dependency_overrides[get_maturity_forecast_service] = (
        lambda: FakeService(error)
    )
    try:
        response = TestClient(app).get(
            "/api/v1/forecasts/usd-cny/maturity-estimate",
            params={"maturity_date": "2026-11-15"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
```

- [ ] **Step 2: Run the API test and verify the route is missing**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_maturity_forecast_api.py -v
```

Expected: collection fails because `backend.routes.forecast` does not exist.

- [ ] **Step 3: Add the forecast route and default service factory**

Create `python/backend/routes/forecast.py`:

```python
from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.forecast.cache import (
    JsonForecastCache,
    default_forecast_cache_path,
)
from backend.forecast.ing import IngForecastProvider
from backend.forecast.schemas import MaturityForecastResponse
from backend.forecast.service import MaturityForecastService
from backend.routes.market import get_market_history_service


router = APIRouter(prefix="/api/v1/forecasts", tags=["forecasts"])


@lru_cache
def get_maturity_forecast_service() -> MaturityForecastService:
    return MaturityForecastService(
        provider=IngForecastProvider(),
        cache=JsonForecastCache(default_forecast_cache_path()),
        market_history_service=get_market_history_service(),
    )


@router.get(
    "/usd-cny/maturity-estimate",
    response_model=MaturityForecastResponse,
)
def usd_cny_maturity_estimate(
    maturity_date: Annotated[date, Query()],
    service: Annotated[
        MaturityForecastService,
        Depends(get_maturity_forecast_service),
    ],
) -> MaturityForecastResponse:
    return service.get_estimate(maturity_date)
```

- [ ] **Step 4: Add the forecast exception handler and register the router**

Add this import and handler to `python/backend/errors.py`:

```python
from backend.forecast.errors import ForecastError


async def forecast_exception_handler(
    _: Request,
    exc: ForecastError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
```

Update `python/backend/main.py` imports:

```python
from backend.errors import (
    forecast_exception_handler,
    market_data_exception_handler,
    probability_calculation_exception_handler,
    validation_exception_handler,
)
from backend.forecast.errors import ForecastError
from backend.routes.forecast import router as forecast_router
```

Register the handler and router inside `create_app()`:

```python
    app.add_exception_handler(ForecastError, forecast_exception_handler)
    app.include_router(forecast_router)
```

- [ ] **Step 5: Run endpoint tests**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_maturity_forecast_api.py -v
```

Expected: the traceable success response and all five stable error mappings pass.

- [ ] **Step 6: Run the complete regression suite**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest -v
```

Expected: every existing and new Python test passes; the pre-existing `StarletteDeprecationWarning` may remain, but no new warning is introduced.

- [ ] **Step 7: Check scope and commit the API**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only the intended forecast route, handler, app registration, and API test remain.

Commit:

```bash
git add python/backend/errors.py python/backend/main.py python/backend/routes/forecast.py python/tests/backend/test_maturity_forecast_api.py
git commit -m "feat: expose ING maturity forecast"
```

---

## Final Verification Checklist

- [ ] Run `cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest -v` and confirm zero failures.
- [ ] Confirm `python/requirements.txt` is unchanged; the implementation uses Python's standard `html.parser` and the existing `httpx` dependency.
- [ ] Confirm `/python/.cache/` remains ignored and no ING or FRED runtime cache is staged by Git.
- [ ] Start FastAPI locally and call `GET /api/v1/forecasts/usd-cny/maturity-estimate?maturity_date=2026-11-15` against live ING.
- [ ] Confirm the first live response uses ING's current USD/CNY points, says `cache_status: live_fetch`, `source_count: 1`, and `is_consensus_forecast: false`.
- [ ] Call the same endpoint again and confirm `cache_status: daily_cache`.
- [ ] Call the endpoint with `maturity_date=2026-08-15` and confirm the first anchor is FRED with its actual observation date.
- [ ] Manually recompute one returned interpolation from its anchor dates and spots.
- [ ] Confirm the ING source update date is no more than 45 days old.
- [ ] Confirm direct or between-ING matching does not invoke FRED in automated tests.
- [ ] Confirm `git status --short` is clean after the final commit.
