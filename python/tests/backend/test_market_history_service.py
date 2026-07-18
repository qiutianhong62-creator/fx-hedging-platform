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
