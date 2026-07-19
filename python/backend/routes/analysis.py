from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.automatic_analysis.schemas import (
    AutomaticNoHedgeProbabilityResponse,
)
from backend.automatic_analysis.service import (
    AutomaticNoHedgeProbabilityService,
)
from backend.models import (
    AnalysisInput,
    NoHedgeProbabilityRequest,
    NoHedgeProbabilityResponse,
    NoHedgeScenarioRequest,
    NoHedgeScenarioResponse,
)
from backend.routes.forecast import get_maturity_forecast_service
from backend.routes.market import get_market_history_service
from backend.services.no_hedge import calculate_no_hedge_scenario
from backend.services.no_hedge_probability import calculate_no_hedge_probability


router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@lru_cache
def get_automatic_no_hedge_probability_service(
) -> AutomaticNoHedgeProbabilityService:
    return AutomaticNoHedgeProbabilityService(
        forecast_service=get_maturity_forecast_service(),
        market_history_service=get_market_history_service(),
    )


@router.post(
    "/no-hedge/scenario",
    response_model=NoHedgeScenarioResponse,
)
def no_hedge_scenario(
    payload: NoHedgeScenarioRequest,
) -> NoHedgeScenarioResponse:
    return calculate_no_hedge_scenario(payload)


@router.post(
    "/no-hedge/probability",
    response_model=NoHedgeProbabilityResponse,
)
def no_hedge_probability(
    payload: NoHedgeProbabilityRequest,
) -> NoHedgeProbabilityResponse:
    return calculate_no_hedge_probability(payload)


@router.post(
    "/no-hedge/automatic-probability",
    response_model=AutomaticNoHedgeProbabilityResponse,
)
def automatic_no_hedge_probability(
    payload: AnalysisInput,
    service: Annotated[
        AutomaticNoHedgeProbabilityService,
        Depends(get_automatic_no_hedge_probability_service),
    ],
) -> AutomaticNoHedgeProbabilityResponse:
    return service.calculate(payload)
