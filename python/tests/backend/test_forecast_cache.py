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
