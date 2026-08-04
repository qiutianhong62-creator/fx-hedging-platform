from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.forecast.cache import JsonForecastCache
from backend.forecast.errors import (
    ForecastFetchError,
    ForecastHorizonInsufficientError,
    ForecastMaturityInvalidError,
    ForecastSourceInvalidError,
    ForecastSourceStaleError,
    ForecastSourceUnavailableError,
)
from backend.forecast.ing import ING_FORECAST_URL
from backend.forecast.institution import InstitutionForecastService
from backend.forecast.mufg import MUFG_FORECAST_URL
from backend.forecast.types import ForecastPoint, InstitutionForecastSnapshot


NOW = datetime(2026, 8, 4, 10, tzinfo=timezone.utc)
SOURCES = (("ING", ING_FORECAST_URL), ("MUFG", MUFG_FORECAST_URL))


def snapshot(
    institution: str,
    source_url: str,
    *,
    fetched_at: datetime = NOW,
    updated_on: date = date(2026, 7, 20),
) -> InstitutionForecastSnapshot:
    return InstitutionForecastSnapshot(
        institution=institution,
        currency_pair="USD/CNY",
        source_url=source_url,
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
        result: InstitutionForecastSnapshot,
        error: Exception | None = None,
    ) -> None:
        self.result = result
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
                observation_date=date(2026, 7, 31),
            )
        )


def make_service(
    tmp_path: Path,
    institution: str,
    source_url: str,
    provider: FakeProvider,
    market: FakeMarketService | None = None,
) -> InstitutionForecastService:
    return InstitutionForecastService(
        provider=provider,
        cache=JsonForecastCache(
            tmp_path / f"{institution.lower()}.json",
            institution=institution,
            source_url=source_url,
        ),
        market_history_service=market or FakeMarketService(),
    )


@pytest.mark.parametrize(("institution", "source_url"), SOURCES)
def test_service_returns_traceable_institution_match(
    tmp_path: Path,
    institution: str,
    source_url: str,
) -> None:
    provider = FakeProvider(snapshot(institution, source_url))

    result = make_service(
        tmp_path,
        institution,
        source_url,
        provider,
    ).get_estimate(
        NOW.date(),
        date(2026, 11, 15),
        now_utc=NOW,
    )

    assert result.institution == institution
    assert result.matched.expected_spot == pytest.approx(6.72)
    assert [item.source for item in result.matched.anchors] == [
        institution,
        institution,
    ]
    assert result.snapshot == snapshot(institution, source_url)
    assert result.cache_status == "live_fetch"
    assert result.cache_age_hours == 0
    assert result.is_stale is False


@pytest.mark.parametrize(("institution", "source_url"), SOURCES)
def test_service_uses_fred_only_before_first_institution_point(
    tmp_path: Path,
    institution: str,
    source_url: str,
) -> None:
    market = FakeMarketService()
    service = make_service(
        tmp_path,
        institution,
        source_url,
        FakeProvider(snapshot(institution, source_url)),
        market,
    )

    result = service.get_estimate(
        NOW.date(),
        date(2026, 8, 31),
        now_utc=NOW,
    )

    assert market.calls == 1
    assert [item.source for item in result.matched.anchors] == [
        "FRED",
        institution,
    ]


def test_daily_cache_avoids_network_fetch(tmp_path: Path) -> None:
    cached = snapshot(
        "ING",
        ING_FORECAST_URL,
        fetched_at=NOW - timedelta(hours=23),
    )
    provider = FakeProvider(cached, error=ForecastFetchError())
    service = make_service(tmp_path, "ING", ING_FORECAST_URL, provider)
    service._cache.save(cached)

    result = service.get_estimate(
        NOW.date(),
        date(2026, 11, 15),
        now_utc=NOW,
    )

    assert provider.calls == 0
    assert result.cache_status == "daily_cache"


def test_network_failure_uses_cache_through_seven_days(tmp_path: Path) -> None:
    cached = snapshot(
        "MUFG",
        MUFG_FORECAST_URL,
        fetched_at=NOW - timedelta(days=6),
    )
    provider = FakeProvider(cached, error=ForecastFetchError())
    service = make_service(tmp_path, "MUFG", MUFG_FORECAST_URL, provider)
    service._cache.save(cached)

    result = service.get_estimate(
        NOW.date(),
        date(2026, 11, 15),
        now_utc=NOW,
    )

    assert provider.calls == 1
    assert result.cache_status == "stale_fallback"
    assert result.is_stale is True


def test_network_failure_rejects_cache_older_than_seven_days(
    tmp_path: Path,
) -> None:
    cached = snapshot(
        "ING",
        ING_FORECAST_URL,
        fetched_at=NOW - timedelta(days=8),
    )
    provider = FakeProvider(cached, error=ForecastFetchError())
    service = make_service(tmp_path, "ING", ING_FORECAST_URL, provider)
    service._cache.save(cached)

    with pytest.raises(ForecastSourceUnavailableError):
        service.get_estimate(
            NOW.date(),
            date(2026, 11, 15),
            now_utc=NOW,
        )


def test_invalid_source_is_not_hidden_by_old_cache(tmp_path: Path) -> None:
    cached = snapshot(
        "MUFG",
        MUFG_FORECAST_URL,
        fetched_at=NOW - timedelta(days=2),
    )
    provider = FakeProvider(cached, error=ForecastSourceInvalidError())
    service = make_service(tmp_path, "MUFG", MUFG_FORECAST_URL, provider)
    service._cache.save(cached)

    with pytest.raises(ForecastSourceInvalidError):
        service.get_estimate(
            NOW.date(),
            date(2026, 11, 15),
            now_utc=NOW,
        )


def test_source_update_older_than_45_days_is_rejected(tmp_path: Path) -> None:
    stale = snapshot(
        "ING",
        ING_FORECAST_URL,
        updated_on=NOW.date() - timedelta(days=46),
    )

    with pytest.raises(ForecastSourceStaleError):
        make_service(
            tmp_path,
            "ING",
            ING_FORECAST_URL,
            FakeProvider(stale),
        ).get_estimate(
            NOW.date(),
            date(2026, 11, 15),
            now_utc=NOW,
        )


def test_invalid_maturity_is_rejected_before_fetch(tmp_path: Path) -> None:
    provider = FakeProvider(snapshot("ING", ING_FORECAST_URL))
    service = make_service(tmp_path, "ING", ING_FORECAST_URL, provider)

    with pytest.raises(ForecastMaturityInvalidError):
        service.get_estimate(NOW.date(), NOW.date(), now_utc=NOW)

    assert provider.calls == 0


def test_date_after_last_point_is_horizon_insufficient(tmp_path: Path) -> None:
    service = make_service(
        tmp_path,
        "MUFG",
        MUFG_FORECAST_URL,
        FakeProvider(snapshot("MUFG", MUFG_FORECAST_URL)),
    )

    with pytest.raises(ForecastHorizonInsufficientError):
        service.get_estimate(
            NOW.date(),
            date(2027, 4, 1),
            now_utc=NOW,
        )
