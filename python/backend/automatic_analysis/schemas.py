from pydantic import BaseModel

from backend.forecast.schemas import MaturityForecastResponse
from backend.forward_strategy.schemas import ForwardStrategyProbabilityResponse
from backend.market.schemas import MarketHistorySummaryResponse
from backend.models import NoHedgeProbabilityResponse


class AutomaticAnalysisDataSources(BaseModel):
    forecast: MaturityForecastResponse
    market_history: MarketHistorySummaryResponse


class AutomaticNoHedgeProbabilityResponse(NoHedgeProbabilityResponse):
    data_sources: AutomaticAnalysisDataSources


class AutomaticForwardStrategyProbabilityResponse(
    ForwardStrategyProbabilityResponse
):
    data_sources: AutomaticAnalysisDataSources
    limitations: list[str]
