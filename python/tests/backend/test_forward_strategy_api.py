from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)
URL = "/api/v1/analysis/forward-strategy/scenario"


def valid_payload() -> dict[str, object]:
    return {
        "currency_pair": "USD/CNY",
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": (date.today() + timedelta(days=180)).isoformat(),
        "target_cny": 6_680_000,
        "assumed_maturity_spot": 6.60,
        "forward_legs": [
            {"notional_usd": 300_000, "forward_rate": 6.80},
            {"notional_usd": 200_000, "forward_rate": 6.75},
        ],
    }


def test_forward_strategy_endpoint_matches_manual_example() -> None:
    response = client.post(URL, json=valid_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "calculated"
    assert body["scenario"]["is_forecast"] is False
    assert body["scenario"]["forward_direction"] == "sell_usd"
    assert body["no_hedge_amount_cny"] == 6_600_000
    assert body["strategy_amount_cny"] == 6_690_000
    assert body["strategy_minus_no_hedge_cny"] == 90_000
    assert body["coverage"]["status"] == "partial_hedge"
    assert body["target_comparison"]["no_hedge"]["target_met"] is False
    assert body["target_comparison"]["strategy"]["target_met"] is True


def test_forward_strategy_endpoint_rejects_empty_legs_friendly() -> None:
    payload = valid_payload()
    payload["forward_legs"] = []

    response = client.post(URL, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["fields"] == [
        {
            "field": "forward_legs",
            "message": "请至少输入一笔远期交易",
        }
    ]


def test_forward_strategy_endpoint_rejects_invalid_forward_rate() -> None:
    payload = valid_payload()
    payload["forward_legs"] = [
        {"notional_usd": 300_000, "forward_rate": 0}
    ]

    response = client.post(URL, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [
        {
            "field": "forward_rate",
            "message": "远期汇率必须是大于 0 的有效数字",
        }
    ]
