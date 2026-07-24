from fastapi import APIRouter

from backend.forward_strategy.schemas import (
    ForwardStrategyScenarioRequest,
    ForwardStrategyScenarioResponse,
)
from backend.forward_strategy.service import (
    calculate_forward_strategy_scenario,
)


router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.post(
    "/forward-strategy/scenario",
    response_model=ForwardStrategyScenarioResponse,
)
def forward_strategy_scenario(
    payload: ForwardStrategyScenarioRequest,
) -> ForwardStrategyScenarioResponse:
    return calculate_forward_strategy_scenario(payload)
