from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def future_date() -> str:
    return (date.today() + timedelta(days=90)).isoformat()


def valid_payload() -> dict[str, object]:
    return {
        "currency_pair": "USD/CNY",
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": future_date(),
        "target_cny": 6_800_000,
    }


def test_validate_endpoint_returns_normalized_input() -> None:
    response = client.post("/api/v1/inputs/validate", json=valid_payload())

    assert response.status_code == 200
    assert response.json() == {
        "status": "valid",
        "quote_convention": "CNY per 1 USD",
        "normalized_input": valid_payload(),
    }


def test_validate_endpoint_allows_target_to_be_omitted() -> None:
    payload = valid_payload()
    payload.pop("target_cny")

    response = client.post("/api/v1/inputs/validate", json=payload)

    assert response.status_code == 200
    assert response.json()["normalized_input"]["target_cny"] is None


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        ("currency_pair", "EUR/CNY", "第一版只支持 USD/CNY"),
        ("exposure_type", "investment", "请选择美元应收、美元应付或持有美元"),
        ("notional_usd", 0, "美元金额必须大于 0"),
        ("target_cny", -1, "目标人民币金额必须大于 0"),
    ],
)
def test_validate_endpoint_returns_friendly_field_errors(
    field: str,
    value: object,
    expected_message: str,
) -> None:
    payload = valid_payload()
    payload[field] = value

    response = client.post("/api/v1/inputs/validate", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "输入内容有误",
            "fields": [{"field": field, "message": expected_message}],
        }
    }


def test_validate_endpoint_rejects_non_future_maturity() -> None:
    payload = valid_payload()
    payload["maturity_date"] = date.today().isoformat()

    response = client.post("/api/v1/inputs/validate", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [
        {"field": "maturity_date", "message": "到期日必须晚于今天"}
    ]
