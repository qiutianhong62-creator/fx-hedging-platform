from datetime import date, timedelta

import pytest

from backend.automatic_analysis.service import (
    AutomaticNoHedgeProbabilityService,
)
from backend.forecast.errors import ForecastSourceUnavailableError
from backend.forecast.schemas import MaturityForecastResponse
from backend.market.errors import MarketDataUnavailableError
from backend.market.schemas import MarketHistorySummaryResponse
from backend.models import AnalysisInput


VALUATION_DATE = date.today()
MATURITY_DATE = VALUATION_DATE + timedelta(days=180)


def forecast_result() -> MaturityForecastResponse:
    return MaturityForecastResponse.model_validate(
        {
            "valuation_date": VALUATION_DATE,
            "maturity_date": MATURITY_DATE,
            "expected_maturity_spot": 6.72,
            "matching": {
                "method": "interpolated",
                "is_system_estimate": True,
                "day_weight": 0.5,
                "anchors": [
                    {"source": "ING", "date": "2026-09-30", "spot": 6.74},
                    {"source": "ING", "date": "2026-12-31", "spot": 6.70},
                ],
            },
            "sources": [
                {
                    "source_updated_date": "2026-07-16",
                    "source_url": "https://think.ing.com/forecasts/",
                    "forecast_points": [
                        {"date": "2026-09-30", "spot": 6.74},
                        {"date": "2026-12-31", "spot": 6.70},
                    ],
                    "cache_status": "daily_cache",
                    "fetched_at_utc": "2026-07-18T10:00:00Z",
                    "cache_age_hours": 2.0,
                    "is_stale": False,
                }
            ],
            "limitations": ["单一机构试验"],
        }
    )


def market_result() -> MarketHistorySummaryResponse:
    return MarketHistorySummaryResponse.model_validate(
        {
            "market_reference": {
                "spot": 6.7766,
                "observation_date": "2026-07-10",
            },
            "historical_volatility": {
                "annualized_volatility_pct": 4.2,
                "window_start": "2025-07-10",
                "window_end": "2026-07-10",
                "observation_count": 250,
                "return_count": 249,
            },
            "source": {
                "fetched_at_utc": "2026-07-18T10:00:00Z",
                "cache_status": "daily_cache",
                "cache_age_hours": 2.0,
                "data_age_days": 8,
                "is_stale": False,
            },
        }
    )


class FakeForecastService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[date] = []

    def get_estimate(self, maturity_date: date) -> MaturityForecastResponse:
        self.calls.append(maturity_date)
        if self.error is not None:
            raise self.error
        return forecast_result()


class FakeMarketService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def get_summary(self) -> MarketHistorySummaryResponse:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return market_result()


def input_payload(target_cny: float | None = 6_800_000) -> AnalysisInput:
    return AnalysisInput(
        exposure_type="usd_receivable",
        notional_usd=1_000_000,
        maturity_date=MATURITY_DATE,
        target_cny=target_cny,
    )


def test_automatic_analysis_uses_ing_spot_and_fred_volatility() -> None:
    forecast = FakeForecastService()
    market = FakeMarketService()
    service = AutomaticNoHedgeProbabilityService(
        forecast_service=forecast,
        market_history_service=market,
    )

    result = service.calculate(input_payload())

    assert forecast.calls == [MATURITY_DATE]
    assert market.calls == 1
    assert result.expected_result.spot == 6.72
    assert result.expected_result.amount_cny == 6_720_000
    assert result.distribution.assumed_expected_maturity_spot == 6.72
    assert result.distribution.assumed_annualized_volatility_pct == 4.2
    assert result.distribution.horizon_days == 180
    assert result.distribution.source_type == "market_data"
    assert result.distribution.is_market_forecast is True
    assert result.target_probability is not None
    assert result.data_sources.forecast == forecast_result()
    assert result.data_sources.market_history == market_result()


def test_automatic_analysis_allows_target_to_be_omitted() -> None:
    result = AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(),
        market_history_service=FakeMarketService(),
    ).calculate(input_payload(target_cny=None))

    assert result.target_probability is None


def test_forecast_failure_stops_before_market_lookup() -> None:
    market = FakeMarketService()
    service = AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(
            error=ForecastSourceUnavailableError()
        ),
        market_history_service=market,
    )

    with pytest.raises(ForecastSourceUnavailableError):
        service.calculate(input_payload())

    assert market.calls == 0


def test_market_failure_is_not_replaced_with_a_default() -> None:
    service = AutomaticNoHedgeProbabilityService(
        forecast_service=FakeForecastService(),
        market_history_service=FakeMarketService(
            error=MarketDataUnavailableError()
        ),
    )

    with pytest.raises(MarketDataUnavailableError):
        service.calculate(input_payload())
