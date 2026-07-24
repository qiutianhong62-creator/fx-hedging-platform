from decimal import Decimal, ROUND_HALF_UP

from backend.models import (
    DifferenceType,
    ExposureType,
    TargetComparison,
)


CNY_CENT = Decimal("0.01")


def decimal_value(value: float) -> Decimal:
    return Decimal(str(value))


def cny_amount(value: Decimal) -> Decimal:
    return value.quantize(CNY_CENT, rounding=ROUND_HALF_UP)


def compare_target(
    *,
    exposure_type: ExposureType,
    amount_cny: Decimal,
    target_cny: float | None,
) -> TargetComparison | None:
    if target_cny is None:
        return None

    target = cny_amount(decimal_value(target_cny))
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
