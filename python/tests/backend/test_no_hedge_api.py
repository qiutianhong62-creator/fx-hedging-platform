from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def valid_payload() -> dict[str, object]:
    return {
        "currency_pair": "USD/CNY",
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": (date.today() + timedelta(days=90)).isoformat(),
        "target_cny": 6_800_000,
        "assumed_maturity_spot": 6.75,
    }


def test_no_hedge_endpoint_returns_assumption_result() -> None:
    response = client.post(
        "/api/v1/analysis/no-hedge/scenario",
        json=valid_payload(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "calculated",
        "quote_convention": "CNY per 1 USD",
        "scenario": {
            "scenario_type": "assumption",
            "is_forecast": False,
            "assumed_maturity_spot": 6.75,
        },
        "result_kind": "cny_proceeds",
        "no_hedge_amount_cny": 6_750_000.0,
        "target_comparison": {
            "target_cny": 6_800_000.0,
            "target_met": False,
            "difference_cny": 50_000.0,
            "difference_type": "shortfall",
        },
    }


def test_no_hedge_endpoint_allows_target_to_be_omitted() -> None:
    payload = valid_payload()
    payload.pop("target_cny")

    response = client.post(
        "/api/v1/analysis/no-hedge/scenario",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["target_comparison"] is None


@pytest.mark.parametrize("assumed_spot", [0, -1])
def test_no_hedge_endpoint_returns_friendly_spot_error(
    assumed_spot: float,
) -> None:
    payload = valid_payload()
    payload["assumed_maturity_spot"] = assumed_spot

    response = client.post(
        "/api/v1/analysis/no-hedge/scenario",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "输入内容有误",
            "fields": [
                {
                    "field": "assumed_maturity_spot",
                    "message": "假设到期汇率必须大于 0",
                }
            ],
        }
    }
