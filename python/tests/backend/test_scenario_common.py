from decimal import Decimal

from backend.models import DifferenceType, ExposureType
from backend.services.scenario_common import cny_amount, compare_target


def test_cny_amount_uses_half_up_rounding() -> None:
    assert cny_amount(Decimal("1.005")) == Decimal("1.01")


def test_compare_target_treats_lower_payable_cost_as_saving() -> None:
    result = compare_target(
        exposure_type=ExposureType.USD_PAYABLE,
        amount_cny=Decimal("6700000.00"),
        target_cny=6_800_000,
    )

    assert result is not None
    assert result.target_met is True
    assert result.difference_cny == 100_000
    assert result.difference_type is DifferenceType.COST_SAVING


def test_compare_target_returns_none_without_target() -> None:
    assert compare_target(
        exposure_type=ExposureType.USD_RECEIVABLE,
        amount_cny=Decimal("6700000.00"),
        target_cny=None,
    ) is None
