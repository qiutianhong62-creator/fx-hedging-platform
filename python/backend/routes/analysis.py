from fastapi import APIRouter

from backend.models import NoHedgeScenarioRequest, NoHedgeScenarioResponse
from backend.services.no_hedge import calculate_no_hedge_scenario


router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.post(
    "/no-hedge/scenario",
    response_model=NoHedgeScenarioResponse,
)
def no_hedge_scenario(
    payload: NoHedgeScenarioRequest,
) -> NoHedgeScenarioResponse:
    return calculate_no_hedge_scenario(payload)
