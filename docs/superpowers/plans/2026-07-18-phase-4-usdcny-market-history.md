# Phase 4 USD/CNY Market History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only market-data endpoint that downloads one year of FRED `DEXCHUS` observations, calculates annualized historical volatility, and returns a traceable non-live USD/CNY reference rate with resilient local caching.

**Architecture:** A provider-specific FRED adapter returns validated observations through a small provider interface. Pure volatility and JSON-cache modules remain independent, while a market-history service applies freshness and fallback rules and a thin FastAPI route exposes the approved response.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, httpx, Python `csv`/`json`/`statistics` standard libraries, pytest, FastAPI `TestClient`.

## Global Constraints

- Currency pair is exactly `USD/CNY`, quoted as `CNY per 1 USD`.
- Primary source is FRED series `DEXCHUS` through the keyless `fredgraph.csv` endpoint.
- Query window is the valuation date minus 365 natural days through the valuation date.
- At least 200 valid positive finite observations are required.
- Annualized volatility is `sample_stddev(daily_log_returns) * sqrt(252) * 100`.
- Missing FRED values (`.` or blank) and natural weekend/holiday gaps are skipped; no zero-return rows are invented.
- A normal cache hit is valid for 24 hours; network-only fallback is valid through 7 days.
- The latest market observation may lag the valuation date by at most 14 natural days.
- The latest FRED value is a reference quote and must always return `is_live_quote: false`.
- No future-rate forecast, implied volatility, database, background scheduler, BIS fallback, or probability-endpoint modification is included.
- Automated tests never call the live FRED website.

---

### Task 1: Build the FRED Observation Provider

**Files:**
- Create: `python/backend/market/__init__.py`
- Create: `python/backend/market/types.py`
- Create: `python/backend/market/errors.py`
- Create: `python/backend/market/fred.py`
- Create: `python/tests/backend/test_fred_market_data.py`

**Interfaces:**
- Consumes: start and end `date` values and an injected `httpx.Client`.
- Produces: `FxObservation`, `HistoryProvider`, `FredHistoryProvider.fetch(start_date, end_date) -> tuple[FxObservation, ...]`, `MarketDataFetchError`, and `MarketDataInvalidError`.

- [ ] **Step 1: Write failing FRED parser and client tests**

Create `python/tests/backend/test_fred_market_data.py`:

```python
from datetime import date

import httpx
import pytest

from backend.market.errors import MarketDataFetchError, MarketDataInvalidError
from backend.market.fred import FredHistoryProvider, parse_fred_csv


def test_parse_fred_csv_cleans_missing_values_sorts_and_deduplicates() -> None:
    csv_text = """observation_date,DEXCHUS
2030-01-03,6.82
2030-01-01,6.80
2030-01-02,.
2030-01-03,6.83
2030-01-04,
"""

    observations = parse_fred_csv(csv_text)

    assert [(item.date.isoformat(), item.rate) for item in observations] == [
        ("2030-01-01", 6.80),
        ("2030-01-03", 6.83),
    ]


@pytest.mark.parametrize(
    "csv_text",
    [
        "date,value\n2030-01-01,6.8\n",
        "observation_date,DEXCHUS\nnot-a-date,6.8\n",
        "observation_date,DEXCHUS\n2030-01-01,nope\n",
        "observation_date,DEXCHUS\n2030-01-01,0\n",
        "observation_date,DEXCHUS\n2030-01-01,-1\n",
        "observation_date,DEXCHUS\n2030-01-01,inf\n",
    ],
)
def test_parse_fred_csv_rejects_invalid_upstream_content(csv_text: str) -> None:
    with pytest.raises(MarketDataInvalidError):
        parse_fred_csv(csv_text)


def test_fred_provider_builds_keyless_csv_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graph/fredgraph.csv"
        assert request.url.params["id"] == "DEXCHUS"
        assert request.url.params["cosd"] == "2029-01-01"
        assert request.url.params["coed"] == "2030-01-01"
        return httpx.Response(
            200,
            text="observation_date,DEXCHUS\n2029-12-31,6.80\n",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = FredHistoryProvider(http_client=client)

    observations = provider.fetch(date(2029, 1, 1), date(2030, 1, 1))

    assert observations[0].rate == 6.80


def test_fred_provider_maps_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    provider = FredHistoryProvider(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(MarketDataFetchError):
        provider.fetch(date(2029, 1, 1), date(2030, 1, 1))


def test_fred_provider_maps_non_success_status() -> None:
    provider = FredHistoryProvider(
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(503, text="unavailable")
            )
        )
    )

    with pytest.raises(MarketDataFetchError):
        provider.fetch(date(2029, 1, 1), date(2030, 1, 1))
```

- [ ] **Step 2: Run the test and verify the market package is missing**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_fred_market_data.py -v
```

Expected: collection fails because `backend.market` does not exist.

- [ ] **Step 3: Define market types and stable exceptions**

Create an empty `python/backend/market/__init__.py`.

Create `python/backend/market/types.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class FxObservation:
    date: date
    rate: float


@dataclass(frozen=True)
class CachedHistory:
    provider: str
    series_id: str
    query_start: date
    query_end: date
    fetched_at_utc: datetime
    observations: tuple[FxObservation, ...]


class HistoryProvider(Protocol):
    def fetch(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[FxObservation, ...]: ...
```

Create `python/backend/market/errors.py`:

```python
class MarketDataError(Exception):
    code = "market_data_error"
    message = "市场数据处理失败"
    status_code = 503


class MarketDataFetchError(Exception):
    pass


class MarketDataUnavailableError(MarketDataError):
    code = "market_data_unavailable"
    message = "历史市场数据暂时不可用，请稍后重试"
    status_code = 503


class MarketDataInvalidError(MarketDataError):
    code = "market_data_invalid"
    message = "市场数据格式异常，请稍后重试"
    status_code = 502


class MarketDataInsufficientError(MarketDataError):
    code = "market_data_insufficient"
    message = "历史有效数据不足，暂时无法计算波动率"
    status_code = 503


class MarketDataStaleError(MarketDataError):
    code = "market_data_stale"
    message = "最新市场数据已经过期，暂时无法计算"
    status_code = 503
```

- [ ] **Step 4: Implement the FRED adapter and strict CSV parser**

Create `python/backend/market/fred.py`:

```python
import csv
from datetime import date
from io import StringIO
from math import isfinite

import httpx

from backend.market.errors import MarketDataFetchError, MarketDataInvalidError
from backend.market.types import FxObservation


FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_SERIES_ID = "DEXCHUS"
REQUEST_TIMEOUT_SECONDS = 10.0


def parse_fred_csv(csv_text: str) -> tuple[FxObservation, ...]:
    reader = csv.DictReader(StringIO(csv_text))
    if reader.fieldnames is None or not {
        "observation_date",
        FRED_SERIES_ID,
    }.issubset(reader.fieldnames):
        raise MarketDataInvalidError()

    by_date: dict[date, FxObservation] = {}
    for row in reader:
        raw_rate = (row.get(FRED_SERIES_ID) or "").strip()
        if raw_rate in {"", "."}:
            continue
        try:
            observation_date = date.fromisoformat(
                (row.get("observation_date") or "").strip()
            )
            rate = float(raw_rate)
        except (TypeError, ValueError) as exc:
            raise MarketDataInvalidError() from exc
        if not isfinite(rate) or rate <= 0:
            raise MarketDataInvalidError()
        by_date[observation_date] = FxObservation(observation_date, rate)

    return tuple(by_date[key] for key in sorted(by_date))


class FredHistoryProvider:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client or httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    def fetch(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[FxObservation, ...]:
        try:
            response = self._http_client.get(
                FRED_CSV_URL,
                params={
                    "id": FRED_SERIES_ID,
                    "cosd": start_date.isoformat(),
                    "coed": end_date.isoformat(),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataFetchError() from exc
        return parse_fred_csv(response.text)
```

- [ ] **Step 5: Run the FRED tests**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_fred_market_data.py -v
```

Expected: all FRED provider tests pass without a live network call.

- [ ] **Step 6: Commit the provider**

```bash
git add python/backend/market python/tests/backend/test_fred_market_data.py
git commit -m "feat: read FRED USD CNY history"
```

---

### Task 2: Calculate Historical Annualized Volatility

**Files:**
- Create: `python/backend/market/volatility.py`
- Create: `python/tests/backend/test_market_volatility.py`

**Interfaces:**
- Consumes: ordered `Sequence[FxObservation]`.
- Produces: `daily_log_returns(observations) -> tuple[float, ...]` and `annualized_volatility_pct(observations) -> float`.

- [ ] **Step 1: Write failing formula tests**

Create `python/tests/backend/test_market_volatility.py`:

```python
from datetime import date, timedelta

import pytest

from backend.market.types import FxObservation
from backend.market.volatility import (
    annualized_volatility_pct,
    daily_log_returns,
)


def observations(rates: list[float]) -> tuple[FxObservation, ...]:
    start = date(2030, 1, 1)
    return tuple(
        FxObservation(start + timedelta(days=index), rate)
        for index, rate in enumerate(rates)
    )


def test_daily_log_returns_use_adjacent_observations() -> None:
    returns = daily_log_returns(observations([6.80, 6.868, 6.79932]))

    assert returns == pytest.approx((0.00995033085, -0.01005033585))


def test_volatility_uses_sample_stddev_and_252_day_annualization() -> None:
    result = annualized_volatility_pct(
        observations([6.80, 6.868, 6.79932])
    )

    assert result == pytest.approx(22.450693, rel=1e-5)


def test_constant_rates_have_zero_historical_volatility() -> None:
    assert annualized_volatility_pct(observations([6.80, 6.80, 6.80])) == 0


def test_volatility_requires_three_price_observations() -> None:
    with pytest.raises(ValueError, match="至少需要3个汇率观察值"):
        annualized_volatility_pct(observations([6.80, 6.81]))
```

- [ ] **Step 2: Run the test and verify the module is missing**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_market_volatility.py -v
```

Expected: collection fails for missing `backend.market.volatility`.

- [ ] **Step 3: Implement the pure formula**

Create `python/backend/market/volatility.py`:

```python
from math import log, sqrt
from statistics import stdev
from typing import Sequence

from backend.market.types import FxObservation


TRADING_DAYS_PER_YEAR = 252


def daily_log_returns(
    observations: Sequence[FxObservation],
) -> tuple[float, ...]:
    return tuple(
        log(current.rate / previous.rate)
        for previous, current in zip(observations, observations[1:])
    )


def annualized_volatility_pct(
    observations: Sequence[FxObservation],
) -> float:
    if len(observations) < 3:
        raise ValueError("至少需要3个汇率观察值")
    returns = daily_log_returns(observations)
    return stdev(returns) * sqrt(TRADING_DAYS_PER_YEAR) * 100
```

- [ ] **Step 4: Run the formula tests**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_market_volatility.py -v
```

Expected: all formula tests pass.

- [ ] **Step 5: Commit the calculator**

```bash
git add python/backend/market/volatility.py python/tests/backend/test_market_volatility.py
git commit -m "feat: calculate historical FX volatility"
```

---

### Task 3: Persist History in an Atomic JSON Cache

**Files:**
- Modify: `.gitignore`
- Create: `python/backend/market/cache.py`
- Create: `python/tests/backend/test_market_cache.py`

**Interfaces:**
- Consumes: a cache `Path` and `CachedHistory` from Task 1.
- Produces: `JsonHistoryCache.load() -> CachedHistory | None`, `JsonHistoryCache.save(history) -> None`, and `default_market_cache_path() -> Path`.

- [ ] **Step 1: Write failing cache tests**

Create `python/tests/backend/test_market_cache.py`:

```python
import json
from datetime import date, datetime, timezone
from pathlib import Path

from backend.market.cache import JsonHistoryCache
from backend.market.types import CachedHistory, FxObservation


def history() -> CachedHistory:
    return CachedHistory(
        provider="FRED",
        series_id="DEXCHUS",
        query_start=date(2029, 1, 1),
        query_end=date(2030, 1, 1),
        fetched_at_utc=datetime(2030, 1, 1, 12, tzinfo=timezone.utc),
        observations=(FxObservation(date(2029, 12, 31), 6.80),),
    )


def test_cache_round_trips_history(tmp_path: Path) -> None:
    cache = JsonHistoryCache(tmp_path / "market.json")

    cache.save(history())

    assert cache.load() == history()


def test_missing_or_corrupt_cache_returns_none(tmp_path: Path) -> None:
    cache_path = tmp_path / "market.json"
    cache = JsonHistoryCache(cache_path)
    assert cache.load() is None

    cache_path.write_text("not-json", encoding="utf-8")
    assert cache.load() is None


def test_schema_valid_but_untrusted_cache_returns_none(tmp_path: Path) -> None:
    cache_path = tmp_path / "market.json"
    cache = JsonHistoryCache(cache_path)
    cache.save(history())
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["series_id"] = "WRONG_SERIES"
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    assert cache.load() is None


def test_save_leaves_no_temporary_file(tmp_path: Path) -> None:
    cache = JsonHistoryCache(tmp_path / "market.json")

    cache.save(history())

    assert [path.name for path in tmp_path.iterdir()] == ["market.json"]
```

- [ ] **Step 2: Run the test and verify the cache module is missing**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_market_cache.py -v
```

Expected: collection fails for missing `backend.market.cache`.

- [ ] **Step 3: Implement atomic JSON persistence**

Create `python/backend/market/cache.py`:

```python
import json
import os
import tempfile
from datetime import date, datetime
from math import isfinite
from pathlib import Path

from backend.market.types import CachedHistory, FxObservation


def default_market_cache_path() -> Path:
    python_root = Path(__file__).resolve().parents[2]
    return python_root / ".cache" / "market-data" / "fred-dexchus-1y.json"


class JsonHistoryCache:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> CachedHistory | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            history = CachedHistory(
                provider=payload["provider"],
                series_id=payload["series_id"],
                query_start=date.fromisoformat(payload["query_start"]),
                query_end=date.fromisoformat(payload["query_end"]),
                fetched_at_utc=datetime.fromisoformat(
                    payload["fetched_at_utc"].replace("Z", "+00:00")
                ),
                observations=tuple(
                    FxObservation(date.fromisoformat(item["date"]), item["rate"])
                    for item in payload["observations"]
                ),
            )
            observation_dates = [item.date for item in history.observations]
            if (
                history.provider != "FRED"
                or history.series_id != "DEXCHUS"
                or history.fetched_at_utc.tzinfo is None
                or history.query_start > history.query_end
                or not history.observations
                or observation_dates != sorted(set(observation_dates))
                or any(
                    not isfinite(item.rate) or item.rate <= 0
                    for item in history.observations
                )
            ):
                return None
            return history
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def save(self, history: CachedHistory) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider": history.provider,
            "series_id": history.series_id,
            "query_start": history.query_start.isoformat(),
            "query_end": history.query_end.isoformat(),
            "fetched_at_utc": history.fetched_at_utc.isoformat().replace(
                "+00:00", "Z"
            ),
            "observations": [
                {"date": item.date.isoformat(), "rate": item.rate}
                for item in history.observations
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

Add this entry to `.gitignore`:

```gitignore
/python/.cache/
```

- [ ] **Step 4: Run cache tests**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_market_cache.py -v
```

Expected: all cache tests pass and no cache is written outside pytest's temporary directory.

- [ ] **Step 5: Commit the cache**

```bash
git add .gitignore python/backend/market/cache.py python/tests/backend/test_market_cache.py
git commit -m "feat: cache FRED market history"
```

---

### Task 4: Orchestrate Freshness, Fallback, and Summary Output

**Files:**
- Create: `python/backend/market/schemas.py`
- Create: `python/backend/market/service.py`
- Create: `python/tests/backend/test_market_history_service.py`

**Interfaces:**
- Consumes: `HistoryProvider`, `JsonHistoryCache`, an injected UTC clock, and Tasks 1–3.
- Produces: `MarketHistoryService.get_summary() -> MarketHistorySummaryResponse` and the approved Pydantic response types.

- [ ] **Step 1: Write failing service tests**

Create `python/tests/backend/test_market_history_service.py` with a fixed clock, a fake provider, and helper observations:

```python
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.market.cache import JsonHistoryCache
from backend.market.errors import (
    MarketDataFetchError,
    MarketDataInsufficientError,
    MarketDataInvalidError,
    MarketDataStaleError,
    MarketDataUnavailableError,
)
from backend.market.service import MarketHistoryService
from backend.market.types import CachedHistory, FxObservation


NOW = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)


def valid_observations(*, latest: date = NOW.date()) -> tuple[FxObservation, ...]:
    start = latest - timedelta(days=249)
    return tuple(
        FxObservation(start + timedelta(days=index), 6.50 + index * 0.001)
        for index in range(250)
    )


class FakeProvider:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or valid_observations()
        self.error = error
        self.calls = 0

    def fetch(self, start_date: date, end_date: date):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def service(tmp_path: Path, provider: FakeProvider) -> MarketHistoryService:
    return MarketHistoryService(
        provider=provider,
        cache=JsonHistoryCache(tmp_path / "market.json"),
        now_utc=lambda: NOW,
    )


def test_no_cache_fetches_writes_and_returns_live_summary(tmp_path: Path) -> None:
    provider = FakeProvider()
    result = service(tmp_path, provider).get_summary()

    assert provider.calls == 1
    assert result.market_reference.spot == pytest.approx(6.749)
    assert result.market_reference.is_live_quote is False
    assert result.historical_volatility.observation_count == 250
    assert result.historical_volatility.return_count == 249
    assert result.source.cache_status == "live_fetch"
    assert (tmp_path / "market.json").exists()


def test_cache_younger_than_24_hours_avoids_fetch(tmp_path: Path) -> None:
    cache = JsonHistoryCache(tmp_path / "market.json")
    cache.save(CachedHistory(
        provider="FRED",
        series_id="DEXCHUS",
        query_start=NOW.date() - timedelta(days=365),
        query_end=NOW.date(),
        fetched_at_utc=NOW - timedelta(hours=23),
        observations=valid_observations(),
    ))
    provider = FakeProvider(error=MarketDataFetchError())

    result = service(tmp_path, provider).get_summary()

    assert provider.calls == 0
    assert result.source.cache_status == "daily_cache"


def test_network_failure_uses_cache_through_seven_days(tmp_path: Path) -> None:
    cache = JsonHistoryCache(tmp_path / "market.json")
    cache.save(CachedHistory(
        provider="FRED",
        series_id="DEXCHUS",
        query_start=NOW.date() - timedelta(days=365),
        query_end=NOW.date(),
        fetched_at_utc=NOW - timedelta(days=6),
        observations=valid_observations(),
    ))
    provider = FakeProvider(error=MarketDataFetchError())

    result = service(tmp_path, provider).get_summary()

    assert provider.calls == 1
    assert result.source.cache_status == "stale_fallback"
    assert result.source.is_stale is True


def test_network_failure_rejects_cache_older_than_seven_days(tmp_path: Path) -> None:
    cache = JsonHistoryCache(tmp_path / "market.json")
    cache.save(CachedHistory(
        provider="FRED",
        series_id="DEXCHUS",
        query_start=NOW.date() - timedelta(days=365),
        query_end=NOW.date(),
        fetched_at_utc=NOW - timedelta(days=8),
        observations=valid_observations(),
    ))

    with pytest.raises(MarketDataUnavailableError):
        service(tmp_path, FakeProvider(error=MarketDataFetchError())).get_summary()


def test_future_dated_cache_is_ignored_and_refetched(tmp_path: Path) -> None:
    cache = JsonHistoryCache(tmp_path / "market.json")
    cache.save(CachedHistory(
        provider="FRED",
        series_id="DEXCHUS",
        query_start=NOW.date() - timedelta(days=365),
        query_end=NOW.date(),
        fetched_at_utc=NOW + timedelta(hours=1),
        observations=valid_observations(),
    ))
    provider = FakeProvider()

    result = service(tmp_path, provider).get_summary()

    assert provider.calls == 1
    assert result.source.cache_status == "live_fetch"


def test_service_rejects_insufficient_stale_and_constant_data(tmp_path: Path) -> None:
    with pytest.raises(MarketDataInsufficientError):
        service(tmp_path, FakeProvider(result=valid_observations()[:199])).get_summary()

    stale = valid_observations(latest=NOW.date() - timedelta(days=15))
    with pytest.raises(MarketDataStaleError):
        service(tmp_path, FakeProvider(result=stale)).get_summary()

    constant = tuple(FxObservation(item.date, 6.80) for item in valid_observations())
    with pytest.raises(MarketDataInvalidError):
        service(tmp_path, FakeProvider(result=constant)).get_summary()
```

- [ ] **Step 2: Run service tests and verify missing modules**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_market_history_service.py -v
```

Expected: collection fails for missing `backend.market.service`.

- [ ] **Step 3: Define response schemas**

Create `python/backend/market/schemas.py`:

```python
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class MarketReference(BaseModel):
    spot: float
    observation_date: date
    is_live_quote: Literal[False] = False


class HistoricalVolatility(BaseModel):
    annualized_volatility_pct: float
    method: Literal["daily_log_returns_sample_stddev"] = (
        "daily_log_returns_sample_stddev"
    )
    trading_days_per_year: Literal[252] = 252
    window: Literal["1y"] = "1y"
    window_start: date
    window_end: date
    observation_count: int
    return_count: int


class MarketDataSource(BaseModel):
    provider: Literal["FRED"] = "FRED"
    series_id: Literal["DEXCHUS"] = "DEXCHUS"
    fetched_at_utc: datetime
    cache_status: Literal["live_fetch", "daily_cache", "stale_fallback"]
    cache_age_hours: float
    data_age_days: int
    is_stale: bool


class MarketHistorySummaryResponse(BaseModel):
    status: Literal["available"] = "available"
    currency_pair: Literal["USD/CNY"] = "USD/CNY"
    quote_convention: Literal["CNY per 1 USD"] = "CNY per 1 USD"
    market_reference: MarketReference
    historical_volatility: HistoricalVolatility
    source: MarketDataSource
```

- [ ] **Step 4: Implement service rules**

Create `python/backend/market/service.py`:

```python
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from math import isfinite

from backend.market.cache import JsonHistoryCache
from backend.market.errors import (
    MarketDataFetchError,
    MarketDataInsufficientError,
    MarketDataInvalidError,
    MarketDataStaleError,
    MarketDataUnavailableError,
)
from backend.market.schemas import (
    HistoricalVolatility,
    MarketDataSource,
    MarketHistorySummaryResponse,
    MarketReference,
)
from backend.market.types import CachedHistory, HistoryProvider
from backend.market.volatility import annualized_volatility_pct


MINIMUM_OBSERVATIONS = 200
NORMAL_CACHE_TTL = timedelta(hours=24)
FALLBACK_CACHE_TTL = timedelta(days=7)
MAX_DATA_AGE_DAYS = 14
WINDOW_DAYS = 365


class MarketHistoryService:
    def __init__(
        self,
        *,
        provider: HistoryProvider,
        cache: JsonHistoryCache,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def get_summary(self) -> MarketHistorySummaryResponse:
        now = self._now_utc()
        cached = self._cache.load()
        cache_age = None if cached is None else now - cached.fetched_at_utc
        if (
            cached is not None
            and cache_age is not None
            and timedelta(0) <= cache_age <= NORMAL_CACHE_TTL
        ):
            return self._build_summary(cached, now, "daily_cache")

        query_end = now.date()
        query_start = query_end - timedelta(days=WINDOW_DAYS)
        try:
            observations = self._provider.fetch(query_start, query_end)
        except MarketDataFetchError as exc:
            if (
                cached is None
                or cache_age is None
                or cache_age < timedelta(0)
                or cache_age > FALLBACK_CACHE_TTL
            ):
                raise MarketDataUnavailableError() from exc
            return self._build_summary(cached, now, "stale_fallback")

        history = CachedHistory(
            provider="FRED",
            series_id="DEXCHUS",
            query_start=query_start,
            query_end=query_end,
            fetched_at_utc=now,
            observations=observations,
        )
        summary = self._build_summary(history, now, "live_fetch")
        self._cache.save(history)
        return summary

    def _build_summary(
        self,
        history: CachedHistory,
        now: datetime,
        cache_status: str,
    ) -> MarketHistorySummaryResponse:
        if len(history.observations) < MINIMUM_OBSERVATIONS:
            raise MarketDataInsufficientError()
        latest = history.observations[-1]
        data_age_days = (now.date() - latest.date).days
        if data_age_days < 0:
            raise MarketDataInvalidError()
        if data_age_days > MAX_DATA_AGE_DAYS:
            raise MarketDataStaleError()

        volatility = annualized_volatility_pct(history.observations)
        if not isfinite(volatility) or volatility <= 0:
            raise MarketDataInvalidError()
        cache_age_hours = max(
            0.0,
            (now - history.fetched_at_utc).total_seconds() / 3600,
        )

        return MarketHistorySummaryResponse(
            market_reference=MarketReference(
                spot=latest.rate,
                observation_date=latest.date,
            ),
            historical_volatility=HistoricalVolatility(
                annualized_volatility_pct=volatility,
                window_start=history.query_start,
                window_end=history.query_end,
                observation_count=len(history.observations),
                return_count=len(history.observations) - 1,
            ),
            source=MarketDataSource(
                fetched_at_utc=history.fetched_at_utc,
                cache_status=cache_status,
                cache_age_hours=cache_age_hours,
                data_age_days=data_age_days,
                is_stale=cache_status == "stale_fallback",
            ),
        )
```

- [ ] **Step 5: Run service tests**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_market_history_service.py -v
```

Expected: all freshness, fallback, quality, and response tests pass.

- [ ] **Step 6: Commit the service**

```bash
git add python/backend/market/schemas.py python/backend/market/service.py python/tests/backend/test_market_history_service.py
git commit -m "feat: summarize USD CNY market history"
```

---

### Task 5: Expose the Read-Only Market History API

**Files:**
- Modify: `python/backend/errors.py`
- Modify: `python/backend/main.py`
- Create: `python/backend/routes/market.py`
- Create: `python/tests/backend/test_market_history_api.py`

**Interfaces:**
- Consumes: `MarketHistoryService`, `MarketHistorySummaryResponse`, and `MarketDataError`.
- Produces: `GET /api/v1/market/usd-cny/history-summary`, dependency-injected service construction, and stable JSON errors.

- [ ] **Step 1: Write failing endpoint tests**

Create `python/tests/backend/test_market_history_api.py`:

```python
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.market.errors import (
    MarketDataInsufficientError,
    MarketDataInvalidError,
    MarketDataStaleError,
    MarketDataUnavailableError,
)
from backend.market.schemas import (
    HistoricalVolatility,
    MarketDataSource,
    MarketHistorySummaryResponse,
    MarketReference,
)
from backend.routes.market import get_market_history_service


class FakeService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def get_summary(self) -> MarketHistorySummaryResponse:
        if self.error is not None:
            raise self.error
        return MarketHistorySummaryResponse(
            market_reference=MarketReference(
                spot=6.80,
                observation_date=date(2030, 1, 1),
            ),
            historical_volatility=HistoricalVolatility(
                annualized_volatility_pct=4.2,
                window_start=date(2029, 1, 1),
                window_end=date(2030, 1, 1),
                observation_count=250,
                return_count=249,
            ),
            source=MarketDataSource(
                fetched_at_utc=datetime(2030, 1, 1, tzinfo=timezone.utc),
                cache_status="live_fetch",
                cache_age_hours=0,
                data_age_days=0,
                is_stale=False,
            ),
        )


def test_market_history_endpoint_returns_traceable_summary() -> None:
    app.dependency_overrides[get_market_history_service] = lambda: FakeService()
    try:
        response = TestClient(app).get(
            "/api/v1/market/usd-cny/history-summary"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["currency_pair"] == "USD/CNY"
    assert body["market_reference"]["spot"] == 6.8
    assert body["market_reference"]["is_live_quote"] is False
    assert body["historical_volatility"]["annualized_volatility_pct"] == 4.2
    assert body["source"]["provider"] == "FRED"
    assert body["source"]["series_id"] == "DEXCHUS"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (MarketDataUnavailableError(), 503, "market_data_unavailable"),
        (MarketDataInvalidError(), 502, "market_data_invalid"),
        (MarketDataInsufficientError(), 503, "market_data_insufficient"),
        (MarketDataStaleError(), 503, "market_data_stale"),
    ],
)
def test_market_history_endpoint_returns_stable_errors(
    error: Exception,
    status: int,
    code: str,
) -> None:
    app.dependency_overrides[get_market_history_service] = lambda: FakeService(error)
    try:
        response = TestClient(app).get(
            "/api/v1/market/usd-cny/history-summary"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
```

- [ ] **Step 2: Run API tests and verify the route is missing**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_market_history_api.py -v
```

Expected: collection fails because `backend.routes.market` does not exist.

- [ ] **Step 3: Add the route and default service factory**

Create `python/backend/routes/market.py`:

```python
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.market.cache import JsonHistoryCache, default_market_cache_path
from backend.market.fred import FredHistoryProvider
from backend.market.schemas import MarketHistorySummaryResponse
from backend.market.service import MarketHistoryService


router = APIRouter(prefix="/api/v1/market", tags=["market"])


@lru_cache
def get_market_history_service() -> MarketHistoryService:
    return MarketHistoryService(
        provider=FredHistoryProvider(),
        cache=JsonHistoryCache(default_market_cache_path()),
    )


@router.get(
    "/usd-cny/history-summary",
    response_model=MarketHistorySummaryResponse,
)
def usd_cny_history_summary(
    service: Annotated[MarketHistoryService, Depends(get_market_history_service)],
) -> MarketHistorySummaryResponse:
    return service.get_summary()
```

- [ ] **Step 4: Add the market exception handler and register the router**

Add imports and handler to `python/backend/errors.py`:

```python
from backend.market.errors import MarketDataError


async def market_data_exception_handler(
    _: Request,
    exc: MarketDataError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
```

Update `python/backend/main.py` imports:

```python
from backend.errors import (
    market_data_exception_handler,
    probability_calculation_exception_handler,
    validation_exception_handler,
)
from backend.market.errors import MarketDataError
from backend.routes.market import router as market_router
```

Register the handler and router inside `create_app()`:

```python
    app.add_exception_handler(MarketDataError, market_data_exception_handler)
    app.include_router(market_router)
```

- [ ] **Step 5: Run endpoint tests**

Run:

```bash
cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest tests/backend/test_market_history_api.py -v
```

Expected: the success response and all four stable error mappings pass.

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

Expected: no whitespace errors; only intended Phase 4 route, handler, main, and API test changes remain.

Commit:

```bash
git add python/backend/errors.py python/backend/main.py python/backend/routes/market.py python/tests/backend/test_market_history_api.py
git commit -m "feat: expose USD CNY market history"
```

---

## Final Verification Checklist

- [ ] Run `cd python && /Users/qiutianhong/Downloads/香港/fx-hedging-platform/.venv/bin/python -m pytest -v` and confirm zero failures.
- [ ] Confirm `python/requirements.txt` is unchanged because httpx is already present.
- [ ] Confirm `/python/.cache/` is ignored and no runtime cache is staged by Git.
- [ ] Start FastAPI locally and call `GET /api/v1/market/usd-cny/history-summary` against live FRED.
- [ ] Confirm the first live response says `cache_status: live_fetch` and `is_live_quote: false`.
- [ ] Call the endpoint again and confirm `cache_status: daily_cache`.
- [ ] Confirm the latest observation is no more than 14 days old and at least 200 observations were used.
- [ ] Confirm `git status --short` is clean after the final commit.
