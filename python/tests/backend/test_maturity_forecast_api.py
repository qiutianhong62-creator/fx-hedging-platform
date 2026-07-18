from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.forecast.errors import (
    ForecastHorizonInsufficientError,
    ForecastMaturityInvalidError,
    ForecastSourceInvalidError,
    ForecastSourceStaleError,
    ForecastSourceUnavailableError,
)
from backend.forecast.schemas import (
    ForecastAnchorResponse,
    ForecastMatchingResponse,
    ForecastPointResponse,
    InstitutionForecastSourceResponse,
    MaturityForecastResponse,
)
from backend.main import app
from backend.routes.forecast import get_maturity_forecast_service


class FakeService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
        if self.error is not None:
            raise self.error
        return MaturityForecastResponse(
            valuation_date=date(2026, 7, 18),
            maturity_date=maturity_date,
            expected_maturity_spot=6.72,
            matching=ForecastMatchingResponse(
                method="interpolated",
                is_system_estimate=True,
                day_weight=0.5,
                anchors=[
                    ForecastAnchorResponse(
                        source="ING",
                        date=date(2026, 9, 30),
                        spot=6.74,
                    ),
                    ForecastAnchorResponse(
                        source="ING",
                        date=date(2026, 12, 31),
                        spot=6.70,
                    ),
                ],
            ),
            sources=[
                InstitutionForecastSourceResponse(
                    source_updated_date=date(2026, 7, 16),
                    source_url="https://think.ing.com/forecasts/",
                    forecast_points=[
                        ForecastPointResponse(
                            date=date(2026, 9, 30),
                            spot=6.74,
                        ),
                        ForecastPointResponse(
                            date=date(2026, 12, 31),
                            spot=6.70,
                        ),
                    ],
                    cache_status="live_fetch",
                    fetched_at_utc=datetime(
                        2026, 7, 18, 10, tzinfo=timezone.utc
                    ),
                    cache_age_hours=0,
                    is_stale=False,
                )
            ],
            limitations=["单一机构试验"],
        )


def test_maturity_forecast_endpoint_returns_traceable_estimate() -> None:
    app.dependency_overrides[get_maturity_forecast_service] = lambda: FakeService()
    try:
        response = TestClient(app).get(
            "/api/v1/forecasts/usd-cny/maturity-estimate",
            params={"maturity_date": "2026-11-15"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["expected_maturity_spot"] == 6.72
    assert body["matching"]["method"] == "interpolated"
    assert body["source_count"] == 1
    assert body["aggregation_status"] == "single_source_trial"
    assert body["is_consensus_forecast"] is False
    assert body["sources"][0]["institution"] == "ING"
    assert body["sources"][0]["source_url"] == (
        "https://think.ing.com/forecasts/"
    )


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
        (ForecastSourceInvalidError(), 502, "forecast_source_invalid"),
        (ForecastSourceStaleError(), 503, "forecast_source_stale"),
    ],
)
def test_maturity_forecast_endpoint_returns_stable_errors(
    error: Exception,
    status: int,
    code: str,
) -> None:
    app.dependency_overrides[get_maturity_forecast_service] = (
        lambda: FakeService(error)
    )
    try:
        response = TestClient(app).get(
            "/api/v1/forecasts/usd-cny/maturity-estimate",
            params={"maturity_date": "2026-11-15"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
