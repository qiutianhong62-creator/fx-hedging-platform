from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.forecast.cache import JsonForecastCache, default_forecast_cache_path
from backend.forecast.ing import IngForecastProvider
from backend.forecast.schemas import MaturityForecastResponse
from backend.forecast.service import MaturityForecastService
from backend.routes.market import get_market_history_service


router = APIRouter(prefix="/api/v1/forecasts", tags=["forecasts"])


@lru_cache
def get_maturity_forecast_service() -> MaturityForecastService:
    return MaturityForecastService(
        provider=IngForecastProvider(),
        cache=JsonForecastCache(default_forecast_cache_path()),
        market_history_service=get_market_history_service(),
    )


@router.get(
    "/usd-cny/maturity-estimate",
    response_model=MaturityForecastResponse,
)
def usd_cny_maturity_estimate(
    maturity_date: Annotated[date, Query()],
    service: Annotated[
        MaturityForecastService,
        Depends(get_maturity_forecast_service),
    ],
) -> MaturityForecastResponse:
    return service.get_estimate(maturity_date)
