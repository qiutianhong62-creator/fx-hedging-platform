from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.forecast.errors import (
    ForecastHorizonInsufficientError,
    ForecastMaturityInvalidError,
    ForecastSourceInvalidError,
    ForecastSourceStaleError,
    ForecastSourceUnavailableError,
    ForecastSourcesUnavailableError,
)
from backend.forecast.schemas import MaturityForecastResponse
from backend.main import app
from backend.routes.forecast import get_maturity_forecast_service


def source_payload(
    institution: str,
    matched_spot: float,
    weight: float,
) -> dict[str, object]:
    source_url = (
        "https://think.ing.com/forecasts/"
        if institution == "ING"
        else "https://mufgresearch.com/forecasts/"
    )
    return {
        "institution": institution,
        "matched_maturity_spot": matched_spot,
        "weight": weight,
        "matching": {
            "method": "interpolated",
            "is_system_estimate": True,
            "day_weight": 0.5,
            "anchors": [
                {
                    "source": institution,
                    "date": "2026-09-30",
                    "spot": matched_spot + 0.02,
                },
                {
                    "source": institution,
                    "date": "2026-12-31",
                    "spot": matched_spot - 0.02,
                },
            ],
        },
        "source_updated_date": "2026-07-16",
        "source_url": source_url,
        "forecast_points": [
            {"date": "2026-09-30", "spot": matched_spot + 0.02},
            {"date": "2026-12-31", "spot": matched_spot - 0.02},
        ],
        "cache_status": "live_fetch",
        "fetched_at_utc": "2026-08-04T10:00:00Z",
        "cache_age_hours": 0,
        "is_stale": False,
    }


def consensus_response(maturity_date: date) -> MaturityForecastResponse:
    return MaturityForecastResponse.model_validate(
        {
            "valuation_date": "2026-08-04",
            "maturity_date": maturity_date,
            "expected_maturity_spot": 6.65,
            "source_count": 2,
            "aggregation_status": "equal_weight_consensus",
            "is_consensus_forecast": True,
            "sources": [
                source_payload("ING", 6.68, 0.5),
                source_payload("MUFG", 6.62, 0.5),
            ],
            "unavailable_sources": [],
            "limitations": ["当前仅包含ING和MUFG两家机构"],
        }
    )


class FakeService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
        if self.error is not None:
            raise self.error
        return consensus_response(maturity_date)


def get_response(service: FakeService):
    app.dependency_overrides[get_maturity_forecast_service] = lambda: service
    try:
        return TestClient(app).get(
            "/api/v1/forecasts/usd-cny/maturity-estimate",
            params={"maturity_date": "2026-11-15"},
        )
    finally:
        app.dependency_overrides.clear()


def test_maturity_forecast_endpoint_returns_traceable_consensus() -> None:
    response = get_response(FakeService())

    assert response.status_code == 200
    body = response.json()
    assert body["expected_maturity_spot"] == 6.65
    assert body["source_count"] == 2
    assert body["aggregation_status"] == "equal_weight_consensus"
    assert body["is_consensus_forecast"] is True
    assert [item["institution"] for item in body["sources"]] == [
        "ING",
        "MUFG",
    ]
    assert [item["weight"] for item in body["sources"]] == [0.5, 0.5]
    assert body["sources"][0]["matching"]["method"] == "interpolated"
    assert "matching" not in body
    assert body["unavailable_sources"] == []


def test_maturity_forecast_endpoint_serializes_single_source_fallback() -> None:
    class FallbackService(FakeService):
        def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
            return MaturityForecastResponse.model_validate(
                {
                    "valuation_date": "2026-08-04",
                    "maturity_date": maturity_date,
                    "expected_maturity_spot": 6.68,
                    "source_count": 1,
                    "aggregation_status": "single_source_fallback",
                    "is_consensus_forecast": False,
                    "sources": [source_payload("ING", 6.68, 1.0)],
                    "unavailable_sources": [
                        {"institution": "MUFG", "reason_code": "fetch_failed"}
                    ],
                    "limitations": ["结果不是多机构综合预测"],
                }
            )

    body = get_response(FallbackService()).json()

    assert body["aggregation_status"] == "single_source_fallback"
    assert body["sources"][0]["weight"] == 1.0
    assert body["unavailable_sources"] == [
        {"institution": "MUFG", "reason_code": "fetch_failed"}
    ]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ForecastMaturityInvalidError(), 422, "forecast_maturity_invalid"),
        (
            ForecastHorizonInsufficientError(),
            503,
            "forecast_horizon_insufficient",
        ),
        (
            ForecastSourceUnavailableError(),
            503,
            "forecast_source_unavailable",
        ),
        (
            ForecastSourcesUnavailableError(),
            503,
            "forecast_sources_unavailable",
        ),
        (ForecastSourceInvalidError(), 502, "forecast_source_invalid"),
        (ForecastSourceStaleError(), 503, "forecast_source_stale"),
    ],
)
def test_maturity_forecast_endpoint_returns_stable_errors(
    error: Exception,
    status: int,
    code: str,
) -> None:
    response = get_response(FakeService(error))

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
