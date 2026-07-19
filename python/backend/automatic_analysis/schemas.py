from pydantic import BaseModel

from backend.forecast.schemas import MaturityForecastResponse
from backend.market.schemas import MarketHistorySummaryResponse
from backend.models import NoHedgeProbabilityResponse


class AutomaticAnalysisDataSources(BaseModel):
    forecast: MaturityForecastResponse
    market_history: MarketHistorySummaryResponse


class AutomaticNoHedgeProbabilityResponse(NoHedgeProbabilityResponse):
    data_sources: AutomaticAnalysisDataSources
