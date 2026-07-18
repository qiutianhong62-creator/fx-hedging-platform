from fastapi import APIRouter

from backend.models import (
    NoHedgeProbabilityRequest,
    NoHedgeProbabilityResponse,
    NoHedgeScenarioRequest,
    NoHedgeScenarioResponse,
)
from backend.services.no_hedge import calculate_no_hedge_scenario
from backend.services.no_hedge_probability import calculate_no_hedge_probability


router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


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
