from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend.automatic_analysis.service import (
    AutomaticNoHedgeProbabilityService,
)
from backend.forecast.errors import (
    ForecastSourceUnavailableError,
    ForecastSourcesUnavailableError,
)
from backend.main import app
from backend.routes.analysis import (
    get_automatic_no_hedge_probability_service,
)
from tests.backend.test_automatic_no_hedge_probability_service import (
    FakeForecastService,
    FakeMarketService,
)


client = TestClient(app)


def valid_payload() -> dict[str, object]:
    return {
        "currency_pair": "USD/CNY",
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": (date.today() + timedelta(days=180)).isoformat(),
        "target_cny": 6_800_000,
    }


def automatic_service() -> AutomaticNoHedgeProbabilityService:
    return AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(),
        market_history_service=FakeMarketService(),
    )


def test_automatic_endpoint_needs_no_assumption_fields() -> None:
    app.dependency_overrides[
        get_automatic_no_hedge_probability_service
    ] = automatic_service
    try:
        response = client.post(
            "/api/v1/analysis/no-hedge/automatic-probability",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["distribution"]["source_type"] == "market_data"
    assert body["distribution"]["is_market_forecast"] is True
    assert body["distribution"]["assumed_expected_maturity_spot"] == 6.65
    assert body["distribution"]["assumed_annualized_volatility_pct"] == 4.2
    assert [
        item["institution"]
        for item in body["data_sources"]["forecast"]["sources"]
    ] == ["ING", "MUFG"]
    assert [
        item["weight"]
        for item in body["data_sources"]["forecast"]["sources"]
    ] == [0.5, 0.5]
    assert body["data_sources"]["market_history"]["source"][
        "provider"
    ] == "FRED"
    assert body["probability_profile"]["bucket_count"] == 20
    assert len(body["probability_profile"]["intervals"]) == 20
    assert body["data_sources"]["forecast"]["aggregation_status"] == (
        "equal_weight_consensus"
    )


def test_automatic_endpoint_keeps_forecast_error_contract() -> None:
    app.dependency_overrides[
        get_automatic_no_hedge_probability_service
    ] = lambda: AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(
            error=ForecastSourceUnavailableError()
        ),
        market_history_service=FakeMarketService(),
    )
    try:
        response = client.post(
            "/api/v1/analysis/no-hedge/automatic-probability",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == (
        "forecast_source_unavailable"
    )


def test_automatic_endpoint_returns_aggregate_forecast_error() -> None:
    app.dependency_overrides[
        get_automatic_no_hedge_probability_service
    ] = lambda: AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(
            error=ForecastSourcesUnavailableError()
        ),
        market_history_service=FakeMarketService(),
    )
    try:
        response = client.post(
            "/api/v1/analysis/no-hedge/automatic-probability",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == (
        "forecast_sources_unavailable"
    )
