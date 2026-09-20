from datetime import date, timedelta
from math import log, sqrt
from statistics import NormalDist

import pytest

from fastapi.testclient import TestClient

from backend.automatic_analysis.service import (
    AutomaticForwardStrategyProbabilityService,
)
from backend.forecast.errors import (
    ForecastSourceUnavailableError,
    ForecastSourcesUnavailableError,
)
from backend.main import app
from backend.routes.forward_strategy import (
    get_automatic_forward_strategy_probability_service,
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
        "forward_legs": [
            {"notional_usd": 500_000, "forward_rate": 6.80},
        ],
    }


def automatic_service() -> AutomaticForwardStrategyProbabilityService:
    return AutomaticForwardStrategyProbabilityService(
        forecast_service=FakeForecastService(),
        market_history_service=FakeMarketService(),
    )


def test_endpoint_returns_strategy_comparison_without_assumptions() -> None:
    app.dependency_overrides[
        get_automatic_forward_strategy_probability_service
    ] = automatic_service
    try:
        response = client.post(
            "/api/v1/analysis/forward-strategy/automatic-probability",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["distribution"]["source_type"] == "market_data"
    assert body["no_hedge"]["expected_amount_cny"] == 6_650_000
    assert body["forward_strategy"]["expected_amount_cny"] == 6_725_000
    assert 0 <= body["comparison"]["probability_strategy_better"] <= 1
    assert body["forward_strategy"]["coverage"]["coverage_ratio"] == 0.5
    assert [
        item["institution"]
        for item in body["data_sources"]["forecast"]["sources"]
    ] == ["ING", "MUFG"]
    assert [
        item["weight"]
        for item in body["data_sources"]["forecast"]["sources"]
    ] == [0.5, 0.5]
    assert (
        body["data_sources"]["market_history"]["source"]["provider"]
        == "FRED"
    )
    assert len(body["limitations"]) == 3
    assert "历史波动率" in body["limitations"][0]
    assert "模型估算" in body["limitations"][1]
    assert "不构成交易或套保建议" in body["limitations"][2]
    profile = body["probability_profile"]
    assert profile["bucket_count"] == 20
    assert len(profile["intervals"]) == 20
    assert profile["lower_tail"]["direction"] == "below"
    assert profile["upper_tail"]["direction"] == "above"
    assert set(profile["intervals"][0]) >= {
        "interval_probability",
        "probability_below_upper",
        "probability_above_upper",
        "no_hedge",
        "forward_strategy",
        "strategy_minus_no_hedge",
    }
    assert set(profile["intervals"][0]["strategy_minus_no_hedge"]) == {
        "minimum_amount_cny",
        "maximum_amount_cny",
    }


def test_endpoint_preserves_forecast_error_contract() -> None:
    app.dependency_overrides[
        get_automatic_forward_strategy_probability_service
    ] = lambda: AutomaticForwardStrategyProbabilityService(
        forecast_service=FakeForecastService(
            error=ForecastSourceUnavailableError()
        ),
        market_history_service=FakeMarketService(),
    )
    try:
        response = client.post(
            "/api/v1/analysis/forward-strategy/automatic-probability",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == (
        "forecast_source_unavailable"
    )


def test_endpoint_returns_aggregate_forecast_error() -> None:
    app.dependency_overrides[
        get_automatic_forward_strategy_probability_service
    ] = lambda: AutomaticForwardStrategyProbabilityService(
        forecast_service=FakeForecastService(
            error=ForecastSourcesUnavailableError()
        ),
        market_history_service=FakeMarketService(),
    )
    try:
        response = client.post(
            "/api/v1/analysis/forward-strategy/automatic-probability",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == (
        "forecast_sources_unavailable"
    )


def test_endpoint_rejects_empty_forward_legs() -> None:
    payload = valid_payload()
    payload["forward_legs"] = []

    response = client.post(
        "/api/v1/analysis/forward-strategy/automatic-probability",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["fields"] == [
        {
            "field": "forward_legs",
            "message": "请至少输入一笔远期交易",
        }
    ]


@pytest.mark.parametrize(
    ("forward_usd", "budget", "critical_spot", "expected_met"),
    [
        (500_000, 6_680_000, 6.56, None),
        (1_000_000, 6_800_000, None, 1.0),
        (1_000_000, 6_799_999.99, None, 0.0),
        (1_200_000, 6_800_000, 6.8, None),
    ],
)
def test_payable_budget_probability_handles_partial_full_and_overhedge(
    forward_usd, budget, critical_spot, expected_met,
) -> None:
    payload = valid_payload()
    payload.update(
        exposure_type="usd_payable",
        target_cny=budget,
        forward_legs=[{"notional_usd": forward_usd, "forward_rate": 6.8}],
    )
    app.dependency_overrides[
        get_automatic_forward_strategy_probability_service
    ] = automatic_service
    try:
        response = client.post(
            "/api/v1/analysis/forward-strategy/automatic-probability",
            json=payload,
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["result_kind"] == "cny_cost"
    strategy = body["forward_strategy"]
    assert strategy["expected_amount_cny"] == pytest.approx(
        forward_usd * 6.8 + (1_000_000 - forward_usd) * 6.65
    )
    target = strategy["target_probability"]
    if critical_spot is None:
        assert target["critical_spot"] is None
    else:
        assert target["critical_spot"] == pytest.approx(critical_spot)
    if expected_met is None:
        # Independent CDF calculation: mean 6.65, annual volatility 4.2%, 180 days.
        sigma = 0.042 * sqrt(180 / 365)
        below = NormalDist().cdf((log(critical_spot / 6.65) + sigma**2 / 2) / sigma)
        expected_met = below if forward_usd < 1_000_000 else 1 - below
    assert target["probability_met"] == pytest.approx(expected_met)
    assert target["probability_missed"] == pytest.approx(1 - expected_met)
    for interval in body["probability_profile"]["intervals"]:
        difference = interval["strategy_minus_no_hedge"]
        assert difference["minimum_amount_cny"] == pytest.approx(
            round(forward_usd * (6.8 - interval["upper_spot"]), 2), abs=0.02,
        )
        assert difference["maximum_amount_cny"] == pytest.approx(
            round(forward_usd * (6.8 - interval["lower_spot"]), 2), abs=0.02,
        )
