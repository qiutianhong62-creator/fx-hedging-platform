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
        "maturity_date": (date.today() + timedelta(days=365)).isoformat(),
        "target_cny": 6_800_000,
        "assumed_expected_maturity_spot": 6.80,
        "assumed_annualized_volatility_pct": 5.0,
    }


def test_probability_endpoint_returns_assumption_analysis() -> None:
    response = client.post(
        "/api/v1/analysis/no-hedge/probability",
        json=valid_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "calculated"
    assert body["quote_convention"] == "CNY per 1 USD"
    assert body["distribution"] == {
        "model_type": "lognormal",
        "source_type": "assumption",
        "is_market_forecast": False,
        "assumed_expected_maturity_spot": 6.8,
        "assumed_annualized_volatility_pct": 5.0,
        "horizon_days": 365,
    }
    assert body["expected_result"] == {
        "spot": 6.8,
        "amount_cny": 6_800_000.0,
    }
    assert body["typical_range_50"]["probability"] == 0.5
    assert body["wide_range_90"]["probability"] == 0.9
    assert body["target_probability"]["probability_met"] == pytest.approx(
        0.4900274818
    )
    assert body["target_probability"]["probability_missed"] == pytest.approx(
        0.5099725182
    )


def test_probability_endpoint_allows_target_to_be_omitted() -> None:
    payload = valid_payload()
    payload.pop("target_cny")

    response = client.post(
        "/api/v1/analysis/no-hedge/probability",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["target_probability"] is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "assumed_expected_maturity_spot",
            0,
            "假设预计到期汇率必须是大于 0 的有效数字",
        ),
        (
            "assumed_annualized_volatility_pct",
            0,
            "假设年化波动率必须是大于 0 的有效数字",
        ),
    ],
)
def test_probability_endpoint_returns_friendly_assumption_errors(
    field: str,
    value: float,
    message: str,
) -> None:
    payload = valid_payload()
    payload[field] = value

    response = client.post(
        "/api/v1/analysis/no-hedge/probability",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "输入内容有误",
            "fields": [{"field": field, "message": message}],
        }
    }


def test_probability_endpoint_returns_stable_calculation_error() -> None:
    payload = valid_payload()
    payload["assumed_annualized_volatility_pct"] = 1e308

    response = client.post(
        "/api/v1/analysis/no-hedge/probability",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "probability_calculation_error",
            "message": "当前假设参数超出可计算范围，请降低波动率后重试",
        }
    }
