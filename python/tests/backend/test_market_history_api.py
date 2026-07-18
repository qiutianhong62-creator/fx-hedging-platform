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
