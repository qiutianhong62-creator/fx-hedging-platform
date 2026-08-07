from dataclasses import dataclass
from typing import Literal

from backend.services.distributions import LognormalDistribution


CORE_LOWER_PROBABILITY = 0.01
CORE_UPPER_PROBABILITY = 0.99
PROFILE_BUCKET_COUNT = 20


@dataclass(frozen=True)
class SpotProbabilityBucket:
    lower_spot: float
    upper_spot: float
    interval_probability: float
    probability_below_upper: float
    probability_above_upper: float


@dataclass(frozen=True)
class SpotProbabilityTail:
    direction: Literal["below", "above"]
    boundary_spot: float
    probability: float


@dataclass(frozen=True)
class SpotProbabilityProfile:
    core_lower_spot: float
    core_upper_spot: float
    core_probability: float
    bucket_count: int
    intervals: tuple[SpotProbabilityBucket, ...]
    lower_tail: SpotProbabilityTail
    upper_tail: SpotProbabilityTail


def build_spot_probability_profile(
    distribution: LognormalDistribution,
) -> SpotProbabilityProfile:
    core_lower_spot = distribution.quantile(CORE_LOWER_PROBABILITY)
    core_upper_spot = distribution.quantile(CORE_UPPER_PROBABILITY)
    bucket_width = (
        core_upper_spot - core_lower_spot
    ) / PROFILE_BUCKET_COUNT
    boundaries = [
        core_lower_spot + bucket_width * index
        for index in range(PROFILE_BUCKET_COUNT)
    ]
    boundaries.append(core_upper_spot)

    intervals = []
    for lower_spot, upper_spot in zip(boundaries, boundaries[1:]):
        probability_below_lower = distribution.cdf(lower_spot)
        probability_below_upper = distribution.cdf(upper_spot)
        intervals.append(
            SpotProbabilityBucket(
                lower_spot=lower_spot,
                upper_spot=upper_spot,
                interval_probability=(
                    probability_below_upper - probability_below_lower
                ),
                probability_below_upper=probability_below_upper,
                probability_above_upper=1.0 - probability_below_upper,
            )
        )

    lower_tail_probability = distribution.cdf(core_lower_spot)
    upper_tail_probability = 1.0 - distribution.cdf(core_upper_spot)
    return SpotProbabilityProfile(
        core_lower_spot=core_lower_spot,
        core_upper_spot=core_upper_spot,
        core_probability=(
            distribution.cdf(core_upper_spot)
            - distribution.cdf(core_lower_spot)
        ),
        bucket_count=PROFILE_BUCKET_COUNT,
        intervals=tuple(intervals),
        lower_tail=SpotProbabilityTail(
            direction="below",
            boundary_spot=core_lower_spot,
            probability=lower_tail_probability,
        ),
        upper_tail=SpotProbabilityTail(
            direction="above",
            boundary_spot=core_upper_spot,
            probability=upper_tail_probability,
        ),
    )
