from backend.models import (
    ExposureType,
    NoHedgeScenarioRequest,
    NoHedgeScenarioResponse,
    ResultKind,
    ScenarioMetadata,
)
from backend.services.scenario_common import (
    cny_amount,
    compare_target,
    decimal_value,
)


def calculate_no_hedge_scenario(
    payload: NoHedgeScenarioRequest,
) -> NoHedgeScenarioResponse:
    amount_cny = cny_amount(
        decimal_value(payload.notional_usd)
        * decimal_value(payload.assumed_maturity_spot)
    )
    result_kind = (
        ResultKind.CNY_COST
        if payload.exposure_type is ExposureType.USD_PAYABLE
        else ResultKind.CNY_PROCEEDS
    )

    return NoHedgeScenarioResponse(
        scenario=ScenarioMetadata(
            assumed_maturity_spot=payload.assumed_maturity_spot,
        ),
        result_kind=result_kind,
        no_hedge_amount_cny=float(amount_cny),
        target_comparison=compare_target(
            exposure_type=payload.exposure_type,
            amount_cny=amount_cny,
            target_cny=payload.target_cny,
        ),
    )
