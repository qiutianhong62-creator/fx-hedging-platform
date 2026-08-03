from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.forward_strategy.schemas import (
    ForwardStrategyProbabilityRequest,
    RangeChange,
)


def valid_payload(**updates) -> dict[str, object]:
    payload: dict[str, object] = {
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": date.today() + timedelta(days=180),
        "target_cny": 6_680_000,
        "forward_legs": [
            {"notional_usd": 300_000, "forward_rate": 6.80},
            {"notional_usd": 200_000, "forward_rate": 6.75},
        ],
    }
    payload.update(updates)
    return payload


def test_probability_request_needs_no_market_assumptions() -> None:
    request = ForwardStrategyProbabilityRequest(**valid_payload())

    assert request.notional_usd == 1_000_000
    assert len(request.forward_legs) == 2
    fields = ForwardStrategyProbabilityRequest.model_fields
    assert "assumed_maturity_spot" not in fields
    assert "assumed_expected_maturity_spot" not in fields
    assert "assumed_annualized_volatility_pct" not in fields


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("notional_usd", float("inf")),
        ("target_cny", float("nan")),
    ],
)
def test_probability_request_rejects_non_finite_amounts(
    field: str,
    value: float,
) -> None:
    with pytest.raises(ValidationError):
        ForwardStrategyProbabilityRequest(
            **valid_payload(**{field: value})
        )


def test_probability_request_requires_a_forward_leg() -> None:
    with pytest.raises(ValidationError):
        ForwardStrategyProbabilityRequest(**valid_payload(forward_legs=[]))


def test_range_change_has_explicit_values() -> None:
    assert RangeChange.REDUCED == "reduced"
    assert RangeChange.UNCHANGED == "unchanged"
    assert RangeChange.INCREASED == "increased"
