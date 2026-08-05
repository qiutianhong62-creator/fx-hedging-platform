from datetime import date, timedelta

import pytest

from backend.automatic_analysis.service import (
    AutomaticForwardStrategyProbabilityService,
)
from backend.forecast.errors import ForecastSourceUnavailableError
from backend.forward_strategy.schemas import ForwardStrategyProbabilityRequest
from backend.market.errors import MarketDataUnavailableError
from tests.backend.test_automatic_no_hedge_probability_service import (
    FakeForecastService,
    FakeMarketService,
    forecast_result,
    market_result,
)


MATURITY_DATE = date.today() + timedelta(days=180)


def payload() -> ForwardStrategyProbabilityRequest:
    return ForwardStrategyProbabilityRequest(
        exposure_type="usd_receivable",
        notional_usd=1_000_000,
        maturity_date=MATURITY_DATE,
        target_cny=6_800_000,
        forward_legs=[
            {"notional_usd": 500_000, "forward_rate": 6.80},
        ],
    )


def test_service_uses_forecast_and_historical_volatility() -> None:
    forecast = FakeForecastService()
    market = FakeMarketService()
    service = AutomaticForwardStrategyProbabilityService(
        forecast_service=forecast,
        market_history_service=market,
    )

    result = service.calculate(payload())

    assert forecast.calls == [MATURITY_DATE]
    assert market.calls == 1
    assert result.distribution.assumed_expected_maturity_spot == 6.65
    assert result.distribution.assumed_annualized_volatility_pct == 4.2
    assert result.data_sources.forecast == forecast_result()
    assert [item.institution for item in result.data_sources.forecast.sources] == [
        "ING",
        "MUFG",
    ]
    assert result.data_sources.market_history == market_result()
    assert any("历史波动率" in item for item in result.limitations)
    assert any("模型估算" in item for item in result.limitations)
    assert any("不构成交易或套保建议" in item for item in result.limitations)


def test_forecast_error_stops_before_market_lookup() -> None:
    market = FakeMarketService()
    service = AutomaticForwardStrategyProbabilityService(
        forecast_service=FakeForecastService(
            error=ForecastSourceUnavailableError()
        ),
        market_history_service=market,
    )

    with pytest.raises(ForecastSourceUnavailableError):
        service.calculate(payload())
    assert market.calls == 0


def test_market_error_is_not_replaced_by_defaults() -> None:
    service = AutomaticForwardStrategyProbabilityService(
        forecast_service=FakeForecastService(),
        market_history_service=FakeMarketService(
            error=MarketDataUnavailableError()
        ),
    )

    with pytest.raises(MarketDataUnavailableError):
        service.calculate(payload())
