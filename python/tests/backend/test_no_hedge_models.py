from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.models import NoHedgeScenarioRequest


def future_date() -> date:
    return date.today() + timedelta(days=90)


def test_no_hedge_request_accepts_positive_assumed_spot() -> None:
    payload = NoHedgeScenarioRequest(
        exposure_type="usd_receivable",
        notional_usd=1_000_000,
        maturity_date=future_date(),
        target_cny=6_800_000,
        assumed_maturity_spot=6.75,
    )

    assert payload.currency_pair == "USD/CNY"
    assert payload.assumed_maturity_spot == 6.75


@pytest.mark.parametrize("assumed_spot", [0, -1])
def test_no_hedge_request_rejects_non_positive_assumed_spot(
    assumed_spot: float,
) -> None:
    with pytest.raises(ValidationError):
        NoHedgeScenarioRequest(
            exposure_type="usd_receivable",
            notional_usd=1_000_000,
            maturity_date=future_date(),
            assumed_maturity_spot=assumed_spot,
        )
