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
    cache.save(snapshot(
        fetched_at=NOW - timedelta(days=6),
        updated_on=date(2026, 7, 10),
    ))

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
    cache.save(snapshot(
        fetched_at=NOW - timedelta(days=8),
        updated_on=date(2026, 7, 10),
    ))

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
