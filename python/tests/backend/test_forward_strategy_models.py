from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.forward_strategy.schemas import (
    ForwardDirection,
    ForwardStrategyScenarioRequest,
)


def valid_request(**updates) -> dict[str, object]:
    payload: dict[str, object] = {
        "exposure_type": "usd_receivable",
        "notional_usd": 1_000_000,
        "maturity_date": date.today() + timedelta(days=180),
        "target_cny": 6_680_000,
        "assumed_maturity_spot": 6.60,
        "forward_legs": [
            {"notional_usd": 300_000, "forward_rate": 6.80},
            {"notional_usd": 200_000, "forward_rate": 6.75},
        ],
    }
    payload.update(updates)
    return payload


def test_request_accepts_multiple_forward_legs() -> None:
    request = ForwardStrategyScenarioRequest(**valid_request())

    assert len(request.forward_legs) == 2
    assert request.forward_legs[0].notional_usd == 300_000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("notional_usd", float("inf")),
        ("target_cny", float("inf")),
        ("assumed_maturity_spot", float("inf")),
    ],
)
def test_request_rejects_non_finite_top_level_values(
    field: str,
    value: float,
) -> None:
    with pytest.raises(ValidationError):
        ForwardStrategyScenarioRequest(**valid_request(**{field: value}))


def test_request_requires_at_least_one_forward_leg() -> None:
    with pytest.raises(ValidationError):
        ForwardStrategyScenarioRequest(**valid_request(forward_legs=[]))


@pytest.mark.parametrize(
    "leg",
    [
        {"notional_usd": 0, "forward_rate": 6.80},
        {"notional_usd": float("inf"), "forward_rate": 6.80},
        {"notional_usd": 300_000, "forward_rate": 0},
        {"notional_usd": 300_000, "forward_rate": float("nan")},
    ],
)
def test_request_rejects_invalid_forward_leg(leg: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        ForwardStrategyScenarioRequest(
            **valid_request(forward_legs=[leg])
        )


def test_direction_enum_uses_explicit_buy_and_sell_values() -> None:
    assert ForwardDirection.SELL_USD == "sell_usd"
    assert ForwardDirection.BUY_USD == "buy_usd"
