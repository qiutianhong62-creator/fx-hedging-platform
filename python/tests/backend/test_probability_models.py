from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.models import NoHedgeProbabilityRequest


def future_date() -> date:
    return date.today() + timedelta(days=365)


def test_probability_request_accepts_positive_finite_assumptions() -> None:
    payload = NoHedgeProbabilityRequest(
        exposure_type="usd_receivable",
        notional_usd=1_000_000,
        maturity_date=future_date(),
        target_cny=6_800_000,
        assumed_expected_maturity_spot=6.80,
        assumed_annualized_volatility_pct=5.0,
    )

    assert payload.currency_pair == "USD/CNY"
    assert payload.assumed_expected_maturity_spot == 6.80
    assert payload.assumed_annualized_volatility_pct == 5.0


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_probability_request_rejects_invalid_expected_spot(value: float) -> None:
    with pytest.raises(ValidationError):
        NoHedgeProbabilityRequest(
            exposure_type="usd_receivable",
            notional_usd=1_000_000,
            maturity_date=future_date(),
            assumed_expected_maturity_spot=value,
            assumed_annualized_volatility_pct=5.0,
        )


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_probability_request_rejects_invalid_volatility(value: float) -> None:
    with pytest.raises(ValidationError):
        NoHedgeProbabilityRequest(
            exposure_type="usd_receivable",
            notional_usd=1_000_000,
            maturity_date=future_date(),
            assumed_expected_maturity_spot=6.80,
            assumed_annualized_volatility_pct=value,
        )
