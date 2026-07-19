from datetime import date
from typing import Protocol

from backend.automatic_analysis.schemas import (
    AutomaticAnalysisDataSources,
    AutomaticNoHedgeProbabilityResponse,
)
from backend.forecast.schemas import MaturityForecastResponse
from backend.market.schemas import MarketHistorySummaryResponse
from backend.models import AnalysisInput, NoHedgeProbabilityRequest
from backend.services.no_hedge_probability import (
    calculate_no_hedge_probability,
)


class ForecastLookup(Protocol):
    def get_estimate(
        self,
        maturity_date: date,
    ) -> MaturityForecastResponse: ...


class MarketHistoryLookup(Protocol):
    def get_summary(self) -> MarketHistorySummaryResponse: ...


class AutomaticNoHedgeProbabilityService:
    def __init__(
        self,
        *,
        forecast_service: ForecastLookup,
        market_history_service: MarketHistoryLookup,
    ) -> None:
        self._forecast_service = forecast_service
        self._market_history_service = market_history_service

    def calculate(
        self,
        payload: AnalysisInput,
    ) -> AutomaticNoHedgeProbabilityResponse:
        forecast = self._forecast_service.get_estimate(payload.maturity_date)
        market_history = self._market_history_service.get_summary()
        probability_input = NoHedgeProbabilityRequest(
            **payload.model_dump(),
            assumed_expected_maturity_spot=(
                forecast.expected_maturity_spot
            ),
            assumed_annualized_volatility_pct=(
                market_history.historical_volatility.annualized_volatility_pct
            ),
        )
        analysis = calculate_no_hedge_probability(
            probability_input,
            valuation_date=forecast.valuation_date,
            source_type="market_data",
            is_market_forecast=True,
        )
        return AutomaticNoHedgeProbabilityResponse(
            **analysis.model_dump(),
            data_sources=AutomaticAnalysisDataSources(
                forecast=forecast,
                market_history=market_history,
            ),
        )
