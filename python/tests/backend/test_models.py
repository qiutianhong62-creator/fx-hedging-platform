from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.models import AnalysisInput, ExposureType


def valid_maturity_date() -> date:
    return date.today() + timedelta(days=90)


def test_analysis_input_accepts_usd_receivable_without_target() -> None:
    payload = AnalysisInput(
        exposure_type=ExposureType.USD_RECEIVABLE,
        notional_usd=1_000_000,
        maturity_date=valid_maturity_date(),
    )

    assert payload.currency_pair == "USD/CNY"
    assert payload.notional_usd == 1_000_000
    assert payload.target_cny is None


def test_analysis_input_accepts_positive_target() -> None:
    payload = AnalysisInput(
        exposure_type=ExposureType.USD_PAYABLE,
        notional_usd=500_000,
        maturity_date=valid_maturity_date(),
        target_cny=3_500_000,
    )

    assert payload.target_cny == 3_500_000


@pytest.mark.parametrize("notional_usd", [0, -1])
def test_analysis_input_rejects_non_positive_notional(notional_usd: float) -> None:
    with pytest.raises(ValidationError):
        AnalysisInput(
            exposure_type=ExposureType.USD_HOLDING,
            notional_usd=notional_usd,
            maturity_date=valid_maturity_date(),
        )


def test_analysis_input_rejects_non_usd_cny_pair() -> None:
    with pytest.raises(ValidationError):
        AnalysisInput(
            currency_pair="EUR/CNY",
            exposure_type=ExposureType.USD_RECEIVABLE,
            notional_usd=1_000_000,
            maturity_date=valid_maturity_date(),
        )


def test_analysis_input_rejects_today_as_maturity() -> None:
    with pytest.raises(ValidationError):
        AnalysisInput(
            exposure_type=ExposureType.USD_RECEIVABLE,
            notional_usd=1_000_000,
            maturity_date=date.today(),
        )


@pytest.mark.parametrize("target_cny", [0, -1])
def test_analysis_input_rejects_non_positive_target(target_cny: float) -> None:
    with pytest.raises(ValidationError):
        AnalysisInput(
            exposure_type=ExposureType.USD_PAYABLE,
            notional_usd=1_000_000,
            maturity_date=valid_maturity_date(),
            target_cny=target_cny,
        )
