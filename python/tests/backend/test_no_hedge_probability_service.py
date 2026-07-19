from datetime import date, timedelta

import pytest

from backend.models import NoHedgeProbabilityRequest, ResultKind
from backend.services.no_hedge_probability import calculate_no_hedge_probability


VALUATION_DATE = date(2030, 1, 1)


def make_payload(
    *,
    exposure_type: str = "usd_receivable",
    target_cny: float | None = 6_800_000,
) -> NoHedgeProbabilityRequest:
    return NoHedgeProbabilityRequest(
        exposure_type=exposure_type,
        notional_usd=1_000_000,
        maturity_date=VALUATION_DATE + timedelta(days=365),
        target_cny=target_cny,
        assumed_expected_maturity_spot=6.80,
        assumed_annualized_volatility_pct=5.0,
    )


def test_probability_analysis_returns_expected_amount_and_ranges() -> None:
    result = calculate_no_hedge_probability(
        make_payload(),
        valuation_date=VALUATION_DATE,
    )

    assert result.result_kind is ResultKind.CNY_PROCEEDS
    assert result.expected_result.spot == 6.80
    assert result.expected_result.amount_cny == 6_800_000.00
    assert result.typical_range_50.probability == 0.50
    assert result.typical_range_50.lower_spot == pytest.approx(6.5662843507)
    assert result.typical_range_50.upper_spot == pytest.approx(7.0244512598)
    assert result.wide_range_90.probability == 0.90
    assert result.wide_range_90.lower_spot == pytest.approx(6.2553051696)
    assert result.wide_range_90.upper_spot == pytest.approx(7.3736681311)
    assert (
        result.typical_range_50.lower_amount_cny
        < result.typical_range_50.upper_amount_cny
    )
    assert (
        result.wide_range_90.lower_amount_cny
        < result.wide_range_90.upper_amount_cny
    )


def test_receivable_and_payable_use_opposite_probability_tails() -> None:
    receivable = calculate_no_hedge_probability(
        make_payload(exposure_type="usd_receivable"),
        valuation_date=VALUATION_DATE,
    )
    payable = calculate_no_hedge_probability(
        make_payload(exposure_type="usd_payable"),
        valuation_date=VALUATION_DATE,
    )

    assert receivable.target_probability is not None
    assert payable.target_probability is not None
    assert receivable.target_probability.probability_met == pytest.approx(
        0.4900274818
    )
    assert payable.target_probability.probability_met == pytest.approx(
        0.5099725182
    )
    assert (
        receivable.target_probability.probability_met
        + receivable.target_probability.probability_missed
    ) == pytest.approx(1.0)


@pytest.mark.parametrize("exposure_type", ["usd_receivable", "usd_holding"])
def test_higher_proceeds_target_reduces_probability_met(
    exposure_type: str,
) -> None:
    lower_target = make_payload(exposure_type=exposure_type)
    higher_target = lower_target.model_copy(update={"target_cny": 7_000_000})

    lower_result = calculate_no_hedge_probability(
        lower_target,
        valuation_date=VALUATION_DATE,
    )
    higher_result = calculate_no_hedge_probability(
        higher_target,
        valuation_date=VALUATION_DATE,
    )

    assert lower_result.target_probability is not None
    assert higher_result.target_probability is not None
    assert (
        higher_result.target_probability.probability_met
        < lower_result.target_probability.probability_met
    )


def test_higher_payable_cost_limit_increases_probability_met() -> None:
    lower_target = make_payload(exposure_type="usd_payable")
    higher_target = lower_target.model_copy(update={"target_cny": 7_000_000})

    lower_result = calculate_no_hedge_probability(
        lower_target,
        valuation_date=VALUATION_DATE,
    )
    higher_result = calculate_no_hedge_probability(
        higher_target,
        valuation_date=VALUATION_DATE,
    )

    assert lower_result.target_probability is not None
    assert higher_result.target_probability is not None
    assert (
        higher_result.target_probability.probability_met
        > lower_result.target_probability.probability_met
    )


def test_probability_analysis_omits_target_when_not_supplied() -> None:
    result = calculate_no_hedge_probability(
        make_payload(target_cny=None),
        valuation_date=VALUATION_DATE,
    )

    assert result.target_probability is None


def test_distribution_metadata_marks_inputs_as_assumptions() -> None:
    result = calculate_no_hedge_probability(
        make_payload(),
        valuation_date=VALUATION_DATE,
    )

    assert result.distribution.model_type == "lognormal"
    assert result.distribution.source_type == "assumption"
    assert result.distribution.is_market_forecast is False
    assert result.distribution.horizon_days == 365


def test_probability_analysis_can_mark_automatic_market_inputs() -> None:
    result = calculate_no_hedge_probability(
        make_payload(),
        valuation_date=VALUATION_DATE,
        source_type="market_data",
        is_market_forecast=True,
    )

    assert result.distribution.source_type == "market_data"
    assert result.distribution.is_market_forecast is True
