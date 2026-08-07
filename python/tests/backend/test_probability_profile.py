from datetime import date, timedelta

import pytest

from backend.services.distributions import build_lognormal_distribution
from backend.services.probability_profile import (
    build_spot_probability_profile,
)


VALUATION_DATE = date(2030, 1, 1)


def make_distribution(*, days: int = 365, volatility_pct: float = 5.0):
    return build_lognormal_distribution(
        expected_spot=6.80,
        annualized_volatility_pct=volatility_pct,
        maturity_date=VALUATION_DATE + timedelta(days=days),
        valuation_date=VALUATION_DATE,
    )


def test_profile_has_twenty_contiguous_equal_width_buckets() -> None:
    profile = build_spot_probability_profile(make_distribution())

    assert profile.bucket_count == 20
    assert len(profile.intervals) == 20
    assert profile.intervals[0].lower_spot == pytest.approx(
        profile.core_lower_spot
    )
    assert profile.intervals[-1].upper_spot == pytest.approx(
        profile.core_upper_spot
    )
    widths = []
    for current, following in zip(
        profile.intervals,
        profile.intervals[1:],
    ):
        assert current.upper_spot == pytest.approx(following.lower_spot)
        widths.append(current.upper_spot - current.lower_spot)
    widths.append(
        profile.intervals[-1].upper_spot
        - profile.intervals[-1].lower_spot
    )
    assert max(widths) == pytest.approx(min(widths))


def test_profile_probabilities_cover_the_full_distribution() -> None:
    distribution = make_distribution()
    profile = build_spot_probability_profile(distribution)

    interval_total = sum(
        interval.interval_probability for interval in profile.intervals
    )
    total = (
        profile.lower_tail.probability
        + interval_total
        + profile.upper_tail.probability
    )
    assert profile.core_probability == pytest.approx(0.98)
    assert profile.lower_tail.probability == pytest.approx(0.01)
    assert profile.upper_tail.probability == pytest.approx(0.01)
    assert total == pytest.approx(1.0)
    for interval in profile.intervals:
        assert interval.interval_probability == pytest.approx(
            distribution.cdf(interval.upper_spot)
            - distribution.cdf(interval.lower_spot)
        )
        assert (
            interval.probability_below_upper
            + interval.probability_above_upper
        ) == pytest.approx(1.0)


def test_profile_cumulative_probabilities_are_monotonic() -> None:
    profile = build_spot_probability_profile(make_distribution())

    below = [item.probability_below_upper for item in profile.intervals]
    above = [item.probability_above_upper for item in profile.intervals]
    assert below == sorted(below)
    assert above == sorted(above, reverse=True)


@pytest.mark.parametrize(
    ("days", "volatility_pct"),
    [(30, 2.0), (365, 5.0), (730, 12.0)],
)
def test_profile_is_finite_and_deterministic(
    days: int,
    volatility_pct: float,
) -> None:
    distribution = make_distribution(
        days=days,
        volatility_pct=volatility_pct,
    )

    first = build_spot_probability_profile(distribution)
    second = build_spot_probability_profile(distribution)

    assert first == second
    assert first.core_lower_spot > 0
    assert first.core_upper_spot > first.core_lower_spot
