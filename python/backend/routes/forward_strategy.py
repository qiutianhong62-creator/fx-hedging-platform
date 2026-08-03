from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.automatic_analysis.schemas import (
    AutomaticForwardStrategyProbabilityResponse,
)
from backend.automatic_analysis.service import (
    AutomaticForwardStrategyProbabilityService,
)
from backend.forward_strategy.schemas import (
    ForwardStrategyProbabilityRequest,
    ForwardStrategyScenarioRequest,
    ForwardStrategyScenarioResponse,
)
from backend.forward_strategy.service import (
    calculate_forward_strategy_scenario,
)
from backend.routes.forecast import get_maturity_forecast_service
from backend.routes.market import get_market_history_service


router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@lru_cache
def get_automatic_forward_strategy_probability_service(
) -> AutomaticForwardStrategyProbabilityService:
    return AutomaticForwardStrategyProbabilityService(
        forecast_service=get_maturity_forecast_service(),
        market_history_service=get_market_history_service(),
    )


@router.post(
    "/forward-strategy/scenario",
    response_model=ForwardStrategyScenarioResponse,
)
def forward_strategy_scenario(
    payload: ForwardStrategyScenarioRequest,
) -> ForwardStrategyScenarioResponse:
    return calculate_forward_strategy_scenario(payload)


@router.post(
    "/forward-strategy/automatic-probability",
    response_model=AutomaticForwardStrategyProbabilityResponse,
)
def automatic_forward_strategy_probability(
    payload: ForwardStrategyProbabilityRequest,
    service: Annotated[
        AutomaticForwardStrategyProbabilityService,
        Depends(get_automatic_forward_strategy_probability_service),
    ],
) -> AutomaticForwardStrategyProbabilityResponse:
    return service.calculate(payload)
