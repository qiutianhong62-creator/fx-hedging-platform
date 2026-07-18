from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.market.cache import JsonHistoryCache, default_market_cache_path
from backend.market.fred import FredHistoryProvider
from backend.market.schemas import MarketHistorySummaryResponse
from backend.market.service import MarketHistoryService


router = APIRouter(prefix="/api/v1/market", tags=["market"])


@lru_cache
def get_market_history_service() -> MarketHistoryService:
    return MarketHistoryService(
        provider=FredHistoryProvider(),
        cache=JsonHistoryCache(default_market_cache_path()),
    )


@router.get(
    "/usd-cny/history-summary",
    response_model=MarketHistorySummaryResponse,
)
def usd_cny_history_summary(
    service: Annotated[MarketHistoryService, Depends(get_market_history_service)],
) -> MarketHistorySummaryResponse:
    return service.get_summary()
