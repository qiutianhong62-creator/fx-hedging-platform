import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.forecast.cache import (
    JsonForecastCache,
    default_ing_forecast_cache_path,
    default_mufg_forecast_cache_path,
)
from backend.forecast.ing import ING_FORECAST_URL
from backend.forecast.mufg import MUFG_FORECAST_URL
from backend.forecast.types import ForecastPoint, InstitutionForecastSnapshot


def snapshot(
    *,
    institution: str = "ING",
    source_url: str = ING_FORECAST_URL,
) -> InstitutionForecastSnapshot:
    return InstitutionForecastSnapshot(
        institution=institution,
        currency_pair="USD/CNY",
        source_url=source_url,
        source_updated_date=date(2026, 7, 16),
        fetched_at_utc=datetime(2026, 7, 18, 10, tzinfo=timezone.utc),
        points=(
            ForecastPoint(date(2026, 9, 30), 6.74),
            ForecastPoint(date(2026, 12, 31), 6.70),
        ),
    )


def ing_cache(path: Path) -> JsonForecastCache:
    return JsonForecastCache(
        path,
        institution="ING",
        source_url=ING_FORECAST_URL,
    )


def test_forecast_cache_round_trips_snapshot(tmp_path: Path) -> None:
    cache = ing_cache(tmp_path / "forecast.json")

    cache.save(snapshot())

    assert cache.load() == snapshot()


def test_missing_or_corrupt_forecast_cache_returns_none(tmp_path: Path) -> None:
    cache_path = tmp_path / "forecast.json"
    cache = ing_cache(cache_path)
    assert cache.load() is None

    cache_path.write_text("not-json", encoding="utf-8")
    assert cache.load() is None


def test_structurally_untrusted_forecast_cache_returns_none(tmp_path: Path) -> None:
    cache_path = tmp_path / "forecast.json"
    cache = ing_cache(cache_path)
    cache.save(snapshot())
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["currency_pair"] = "CNY/USD"
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    assert cache.load() is None


@pytest.mark.parametrize(
    ("institution", "source_url"),
    [("ING", ING_FORECAST_URL), ("MUFG", MUFG_FORECAST_URL)],
)
@pytest.mark.parametrize("corruption", ["duplicate", "nonpositive"])
def test_forecast_cache_rejects_invalid_points(
    tmp_path: Path,
    institution: str,
    source_url: str,
    corruption: str,
) -> None:
    cache_path = tmp_path / "forecast.json"
    cache = JsonForecastCache(
        cache_path,
        institution=institution,
        source_url=source_url,
    )
    cache.save(snapshot(institution=institution, source_url=source_url))
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    if corruption == "duplicate":
        payload["points"][1]["date"] = payload["points"][0]["date"]
    else:
        payload["points"][1]["spot"] = -1
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    assert cache.load() is None


def test_forecast_cache_atomic_save_leaves_no_temp_file(tmp_path: Path) -> None:
    cache = ing_cache(tmp_path / "forecast.json")

    cache.save(snapshot())

    assert [path.name for path in tmp_path.iterdir()] == ["forecast.json"]


def test_ing_and_mufg_default_cache_paths_are_independent() -> None:
    assert default_ing_forecast_cache_path().name == "ing-usdcny-forecast.json"
    assert default_mufg_forecast_cache_path().name == "mufg-usdcny-forecast.json"
    assert default_ing_forecast_cache_path() != default_mufg_forecast_cache_path()


def test_cache_rejects_snapshot_for_another_institution(tmp_path: Path) -> None:
    path = tmp_path / "forecast.json"
    ing_cache(path).save(snapshot())

    mufg_cache = JsonForecastCache(
        path,
        institution="MUFG",
        source_url=MUFG_FORECAST_URL,
    )

    assert mufg_cache.load() is None


def test_mufg_cache_round_trips_official_snapshot(tmp_path: Path) -> None:
    cache = JsonForecastCache(
        tmp_path / "mufg.json",
        institution="MUFG",
        source_url=MUFG_FORECAST_URL,
    )
    expected = snapshot(
        institution="MUFG",
        source_url=MUFG_FORECAST_URL,
    )

    cache.save(expected)

    assert cache.load() == expected
