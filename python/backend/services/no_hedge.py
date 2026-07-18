from decimal import Decimal, ROUND_HALF_UP

from backend.models import (
    DifferenceType,
    ExposureType,
    NoHedgeScenarioRequest,
    NoHedgeScenarioResponse,
    ResultKind,
    ScenarioMetadata,
    TargetComparison,
)


CNY_CENT = Decimal("0.01")


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _cny(value: Decimal) -> Decimal:
    return value.quantize(CNY_CENT, rounding=ROUND_HALF_UP)


def _target_comparison(
    *,
    exposure_type: ExposureType,
    amount_cny: Decimal,
    target_cny: float | None,
) -> TargetComparison | None:
    if target_cny is None:
        return None

    target = _cny(_decimal(target_cny))
    if amount_cny == target:
        return TargetComparison(
            target_cny=float(target),
            target_met=True,
            difference_cny=0.0,
            difference_type=DifferenceType.ON_TARGET,
        )

    if exposure_type is ExposureType.USD_PAYABLE:
        target_met = amount_cny < target
        difference_type = (
            DifferenceType.COST_SAVING
            if target_met
            else DifferenceType.EXCESS_COST
        )
    else:
        target_met = amount_cny > target
        difference_type = (
            DifferenceType.SURPLUS
            if target_met
            else DifferenceType.SHORTFALL
        )

    return TargetComparison(
        target_cny=float(target),
        target_met=target_met,
        difference_cny=float(abs(amount_cny - target)),
        difference_type=difference_type,
    )


def calculate_no_hedge_scenario(
    payload: NoHedgeScenarioRequest,
) -> NoHedgeScenarioResponse:
    amount_cny = _cny(
        _decimal(payload.notional_usd)
        * _decimal(payload.assumed_maturity_spot)
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
        target_comparison=_target_comparison(
            exposure_type=payload.exposure_type,
            amount_cny=amount_cny,
            target_cny=payload.target_cny,
        ),
    )
