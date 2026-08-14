from datetime import date
from decimal import Decimal
from typing import Literal

from backend.models import (
    DistributionMetadata,
    ExpectedResult,
    ExposureType,
    NoHedgeProbabilityProfile,
    NoHedgeProbabilityProfileInterval,
    NoHedgeProbabilityProfileTail,
    NoHedgeProbabilityRequest,
    NoHedgeProbabilityResponse,
    NoHedgeScenarioRequest,
    ProbabilityRange,
    ResultKind,
    TargetProbability,
)
from backend.services.distributions import (
    LognormalDistribution,
    build_lognormal_distribution,
)
from backend.services.no_hedge import calculate_no_hedge_scenario
from backend.services.probability_profile import (
    build_spot_probability_profile,
)


def _amount_at_spot(
    payload: NoHedgeProbabilityRequest,
    spot: float,
) -> float:
    scenario = NoHedgeScenarioRequest(
        currency_pair=payload.currency_pair,
        exposure_type=payload.exposure_type,
        notional_usd=payload.notional_usd,
        maturity_date=payload.maturity_date,
        target_cny=None,
        assumed_maturity_spot=spot,
    )
    return calculate_no_hedge_scenario(scenario).no_hedge_amount_cny


def _probability_range(
    payload: NoHedgeProbabilityRequest,
    distribution: LognormalDistribution,
    *,
    probability: float,
    lower_percentile: float,
    upper_percentile: float,
) -> ProbabilityRange:
    lower_spot = distribution.quantile(lower_percentile)
    upper_spot = distribution.quantile(upper_percentile)
    return ProbabilityRange(
        probability=probability,
        lower_spot=lower_spot,
        upper_spot=upper_spot,
        lower_amount_cny=_amount_at_spot(payload, lower_spot),
        upper_amount_cny=_amount_at_spot(payload, upper_spot),
    )


def _target_probability(
    payload: NoHedgeProbabilityRequest,
    distribution: LognormalDistribution,
) -> TargetProbability | None:
    if payload.target_cny is None:
        return None

    critical_spot_decimal = (
        Decimal(str(payload.target_cny))
        / Decimal(str(payload.notional_usd))
    )
    critical_spot = float(critical_spot_decimal)
    probability_below = distribution.cdf(critical_spot)
    if payload.exposure_type is ExposureType.USD_PAYABLE:
        probability_met = probability_below
    else:
        probability_met = 1.0 - probability_below
    probability_met = min(1.0, max(0.0, probability_met))

    return TargetProbability(
        target_cny=payload.target_cny,
        critical_spot=critical_spot,
        probability_met=probability_met,
        probability_missed=1.0 - probability_met,
    )


def _no_hedge_probability_profile(
    payload: NoHedgeProbabilityRequest,
    distribution: LognormalDistribution,
) -> NoHedgeProbabilityProfile:
    spot_profile = build_spot_probability_profile(distribution)
    intervals = []
    for interval in spot_profile.intervals:
        lower_amount = _amount_at_spot(payload, interval.lower_spot)
        upper_amount = _amount_at_spot(payload, interval.upper_spot)
        intervals.append(
            NoHedgeProbabilityProfileInterval(
                lower_spot=interval.lower_spot,
                upper_spot=interval.upper_spot,
                interval_probability=interval.interval_probability,
                probability_below_upper=(
                    interval.probability_below_upper
                ),
                probability_above_upper=(
                    interval.probability_above_upper
                ),
                minimum_amount_cny=min(lower_amount, upper_amount),
                maximum_amount_cny=max(lower_amount, upper_amount),
            )
        )

    return NoHedgeProbabilityProfile(
        core_lower_spot=spot_profile.core_lower_spot,
        core_upper_spot=spot_profile.core_upper_spot,
        core_probability=spot_profile.core_probability,
        bucket_count=spot_profile.bucket_count,
        intervals=intervals,
        lower_tail=NoHedgeProbabilityProfileTail(
            direction=spot_profile.lower_tail.direction,
            boundary_spot=spot_profile.lower_tail.boundary_spot,
            probability=spot_profile.lower_tail.probability,
            boundary_amount_cny=_amount_at_spot(
                payload,
                spot_profile.lower_tail.boundary_spot,
            ),
        ),
        upper_tail=NoHedgeProbabilityProfileTail(
            direction=spot_profile.upper_tail.direction,
            boundary_spot=spot_profile.upper_tail.boundary_spot,
            probability=spot_profile.upper_tail.probability,
            boundary_amount_cny=_amount_at_spot(
                payload,
                spot_profile.upper_tail.boundary_spot,
            ),
        ),
    )


def calculate_no_hedge_probability(
    payload: NoHedgeProbabilityRequest,
    *,
    valuation_date: date | None = None,
    source_type: Literal["assumption", "market_data"] = "assumption",
    is_market_forecast: bool = False,
) -> NoHedgeProbabilityResponse:
    distribution = build_lognormal_distribution(
        expected_spot=payload.assumed_expected_maturity_spot,
        annualized_volatility_pct=payload.assumed_annualized_volatility_pct,
        maturity_date=payload.maturity_date,
        valuation_date=valuation_date,
    )
    result_kind = (
        ResultKind.CNY_COST
        if payload.exposure_type is ExposureType.USD_PAYABLE
        else ResultKind.CNY_PROCEEDS
    )

    return NoHedgeProbabilityResponse(
        distribution=DistributionMetadata(
            source_type=source_type,
            is_market_forecast=is_market_forecast,
            assumed_expected_maturity_spot=(
                payload.assumed_expected_maturity_spot
            ),
            assumed_annualized_volatility_pct=(
                payload.assumed_annualized_volatility_pct
            ),
            horizon_days=distribution.horizon_days,
        ),
        result_kind=result_kind,
        expected_result=ExpectedResult(
            spot=payload.assumed_expected_maturity_spot,
            amount_cny=_amount_at_spot(
                payload,
                payload.assumed_expected_maturity_spot,
            ),
        ),
        typical_range_50=_probability_range(
            payload,
            distribution,
            probability=0.50,
            lower_percentile=0.25,
            upper_percentile=0.75,
        ),
        wide_range_90=_probability_range(
            payload,
            distribution,
            probability=0.90,
            lower_percentile=0.05,
            upper_percentile=0.95,
        ),
        target_probability=_target_probability(payload, distribution),
        probability_profile=_no_hedge_probability_profile(
            payload,
            distribution,
        ),
    )
