from datetime import date, timedelta

import pytest

from backend.models import (
    DifferenceType,
    NoHedgeScenarioRequest,
    ResultKind,
)
from backend.services.no_hedge import calculate_no_hedge_scenario


def make_payload(
    *,
    exposure_type: str = "usd_receivable",
    notional_usd: float = 1_000_000,
    assumed_spot: float = 6.75,
    target_cny: float | None = 6_800_000,
) -> NoHedgeScenarioRequest:
    return NoHedgeScenarioRequest(
        exposure_type=exposure_type,
        notional_usd=notional_usd,
        maturity_date=date.today() + timedelta(days=90),
        target_cny=target_cny,
        assumed_maturity_spot=assumed_spot,
    )


@pytest.mark.parametrize(
    ("exposure_type", "expected_kind"),
    [
        ("usd_receivable", ResultKind.CNY_PROCEEDS),
        ("usd_holding", ResultKind.CNY_PROCEEDS),
        ("usd_payable", ResultKind.CNY_COST),
    ],
)
def test_calculation_assigns_business_meaning(
    exposure_type: str,
    expected_kind: ResultKind,
) -> None:
    result = calculate_no_hedge_scenario(
        make_payload(exposure_type=exposure_type)
    )

    assert result.result_kind is expected_kind
    assert result.no_hedge_amount_cny == 6_750_000.00
    assert result.scenario.scenario_type == "assumption"
    assert result.scenario.is_forecast is False


@pytest.mark.parametrize(
    (
        "exposure_type",
        "assumed_spot",
        "target_cny",
        "target_met",
        "difference_cny",
        "difference_type",
    ),
    [
        (
            "usd_receivable",
            6.80,
            6_800_000,
            True,
            0.00,
            DifferenceType.ON_TARGET,
        ),
        (
            "usd_receivable",
            6.90,
            6_800_000,
            True,
            100_000.00,
            DifferenceType.SURPLUS,
        ),
        (
            "usd_holding",
            6.70,
            6_800_000,
            False,
            100_000.00,
            DifferenceType.SHORTFALL,
        ),
        (
            "usd_payable",
            6.70,
            6_800_000,
            True,
            100_000.00,
            DifferenceType.COST_SAVING,
        ),
        (
            "usd_payable",
            6.90,
            6_800_000,
            False,
            100_000.00,
            DifferenceType.EXCESS_COST,
        ),
    ],
)
def test_calculation_compares_target_by_exposure_direction(
    exposure_type: str,
    assumed_spot: float,
    target_cny: float,
    target_met: bool,
    difference_cny: float,
    difference_type: DifferenceType,
) -> None:
    result = calculate_no_hedge_scenario(
        make_payload(
            exposure_type=exposure_type,
            assumed_spot=assumed_spot,
            target_cny=target_cny,
        )
    )

    assert result.target_comparison is not None
    assert result.target_comparison.target_met is target_met
    assert result.target_comparison.difference_cny == difference_cny
    assert result.target_comparison.difference_type is difference_type


def test_calculation_omits_comparison_without_target() -> None:
    result = calculate_no_hedge_scenario(make_payload(target_cny=None))

    assert result.target_comparison is None


def test_calculation_rounds_half_up_to_cny_cent() -> None:
    result = calculate_no_hedge_scenario(
        make_payload(
            notional_usd=1.005,
            assumed_spot=1,
            target_cny=None,
        )
    )

    assert result.no_hedge_amount_cny == 1.01
