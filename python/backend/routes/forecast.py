from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.forecast.cache import (
    JsonForecastCache,
    default_ing_forecast_cache_path,
    default_mufg_forecast_cache_path,
)
from backend.forecast.ing import ING_FORECAST_URL, IngForecastProvider
from backend.forecast.institution import InstitutionForecastService
from backend.forecast.mufg import MUFG_FORECAST_URL, MufgForecastProvider
from backend.forecast.schemas import MaturityForecastResponse
from backend.forecast.service import MaturityForecastService
from backend.routes.market import get_market_history_service


router = APIRouter(prefix="/api/v1/forecasts", tags=["forecasts"])


@lru_cache
def get_maturity_forecast_service() -> MaturityForecastService:
    market_history_service = get_market_history_service()
    ing = InstitutionForecastService(
        provider=IngForecastProvider(),
        cache=JsonForecastCache(
            default_ing_forecast_cache_path(),
            institution="ING",
            source_url=ING_FORECAST_URL,
        ),
        market_history_service=market_history_service,
    )
    mufg = InstitutionForecastService(
        provider=MufgForecastProvider(),
        cache=JsonForecastCache(
            default_mufg_forecast_cache_path(),
            institution="MUFG",
            source_url=MUFG_FORECAST_URL,
        ),
        market_history_service=market_history_service,
    )
    return MaturityForecastService(
        institution_services=(("ING", ing), ("MUFG", mufg)),
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
