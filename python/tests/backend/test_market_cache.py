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
