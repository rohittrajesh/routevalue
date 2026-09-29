"""Pure decision logic for comparing RouteValue route candidates."""

from collections.abc import Sequence
from decimal import Decimal

from routevalue.domain.models import (
    DecisionCandidate,
    DecisionReason,
    DecisionResult,
    RouteCandidate,
)
from routevalue.domain.units import Money, MoneyPerHour, seconds_to_hours

GENERALIZED_COST_TIE_TOLERANCE: Money = Decimal("0.10")

def is_numerical_tie(
    first_cost: Money,
    second_cost: Money,
) -> bool:
    """Return whether two generalized costs are within the V1 tie tolerance."""

    return abs(first_cost - second_cost) < GENERALIZED_COST_TIE_TOLERANCE

def resolve_numerical_tie(
    tied_candidates: Sequence[DecisionCandidate],
) -> DecisionCandidate:
    """Resolve a numerical tie using the deterministic V1 tie-break order."""

    winner, _ = _resolve_numerical_tie_with_reason(tied_candidates)

    return winner

def _resolve_numerical_tie_with_reason(
    tied_candidates: Sequence[DecisionCandidate],
) -> tuple[DecisionCandidate, DecisionReason]:
    """Resolve a numerical tie and report the criterion that decided it."""

    if len(tied_candidates) < 2:
        raise ValueError(
            "at least two candidates are required to resolve a numerical tie"
        )

    fastest_duration = min(
        candidate.route.duration_seconds
        for candidate in tied_candidates
    )
    finalists = [
        candidate
        for candidate in tied_candidates
        if candidate.route.duration_seconds == fastest_duration
    ]

    if len(finalists) == 1:
        return (
            finalists[0],
            DecisionReason.NUMERICAL_TIE_FASTER_WINS,
        )

    lowest_monetary_cost = min(
        calculate_monetary_cost(candidate)
        for candidate in finalists
    )
    finalists = [
        candidate
        for candidate in finalists
        if calculate_monetary_cost(candidate) == lowest_monetary_cost
    ]

    if len(finalists) == 1:
        return (
            finalists[0],
            DecisionReason.NUMERICAL_TIE_CHEAPER_WINS,
        )

    shortest_distance = min(
        candidate.route.distance_meters
        for candidate in finalists
    )
    finalists = [
        candidate
        for candidate in finalists
        if candidate.route.distance_meters == shortest_distance
    ]

    if len(finalists) == 1:
        return (
            finalists[0],
            DecisionReason.NUMERICAL_TIE_SHORTER_DISTANCE_WINS,
        )

    return (
        finalists[0],
        DecisionReason.NUMERICAL_TIE_STABLE_ORDER_WINS,
    )

def _determine_standard_decision_reason(
    winner: DecisionCandidate,
    comparison_candidate: DecisionCandidate,
) -> DecisionReason:
    """Explain a normal generalized-cost win against the best alternative."""

    winner_duration = winner.route.duration_seconds
    comparison_duration = comparison_candidate.route.duration_seconds

    winner_monetary_cost = calculate_monetary_cost(winner)
    comparison_monetary_cost = calculate_monetary_cost(comparison_candidate)

    if (
        winner_duration <= comparison_duration
        and winner_monetary_cost <= comparison_monetary_cost
    ):
        return DecisionReason.FASTER_AND_CHEAPER

    if winner_duration < comparison_duration:
        return DecisionReason.FASTER_ROUTE_WORTH_EXTRA_COST

    return DecisionReason.CHEAPER_ROUTE_WORTH_EXTRA_TIME

def calculate_monetary_cost(candidate: DecisionCandidate) -> Money:
    """Calculate the route's direct monetary cost."""

    if candidate.route.toll_cost is None:
        raise ValueError("toll_cost is required to score a route")

    return candidate.route.toll_cost + candidate.energy_estimate.cost

def calculate_time_cost(
    route: RouteCandidate,
    value_of_time_per_hour: MoneyPerHour,
) -> Money:
    """Convert a route's travel time into monetary value."""

    if value_of_time_per_hour < 0:
        raise ValueError("value_of_time_per_hour cannot be negative")

    return value_of_time_per_hour * seconds_to_hours(route.duration_seconds)


def calculate_generalized_cost(
    candidate: DecisionCandidate,
    value_of_time_per_hour: MoneyPerHour,
) -> Money:
    """Calculate the generalized cost of a route."""

    monetary_cost = calculate_monetary_cost(candidate)
    time_cost = calculate_time_cost(
        candidate.route,
        value_of_time_per_hour,
    )

    return monetary_cost + time_cost

def select_lowest_generalized_cost_candidate(
    eligible_candidates: Sequence[DecisionCandidate],
    value_of_time_per_hour: MoneyPerHour,
) -> DecisionCandidate:
    """Select the unique candidate with the lowest exact generalized cost."""

    if len(eligible_candidates) < 2:
        raise ValueError("at least two candidates are required for comparison")

    scored_candidates = [
        (
            candidate,
            calculate_generalized_cost(candidate, value_of_time_per_hour),
        )
        for candidate in eligible_candidates
    ]

    lowest_cost = min(cost for _, cost in scored_candidates)

    lowest_candidates = [
    candidate
    for candidate, cost in scored_candidates
    if is_numerical_tie(cost, lowest_cost)
]

    if len(lowest_candidates) == 1:
        return lowest_candidates[0]

    return resolve_numerical_tie(lowest_candidates)

def decide_route(
    eligible_candidates: Sequence[DecisionCandidate],
    *,
    value_of_time_per_hour: MoneyPerHour,
    candidate_count: int,
    missing_data_present: bool,
) -> DecisionResult:
    """Choose the best route from candidates that passed eligibility checks."""

    if value_of_time_per_hour < 0:
        raise ValueError("value_of_time_per_hour cannot be negative")

    eligible_count = len(eligible_candidates)

    if eligible_count == 0:
        return DecisionResult(
            recommended_route=None,
            reason=None,
            numerical_tie=False,
            missing_data_present=missing_data_present,
            candidate_count=candidate_count,
            eligible_count=0,
        )

    if eligible_count == 1:
        return DecisionResult(
            recommended_route=eligible_candidates[0].route,
            reason=DecisionReason.ONLY_ELIGIBLE_ROUTE,
            numerical_tie=False,
            missing_data_present=missing_data_present,
            candidate_count=candidate_count,
            eligible_count=1,
        )

    scored_candidates = [
        (
            candidate,
            calculate_generalized_cost(candidate, value_of_time_per_hour),
        )
        for candidate in eligible_candidates
    ]

    lowest_cost = min(cost for _, cost in scored_candidates)

    tied_candidates = [
        candidate
        for candidate, cost in scored_candidates
        if is_numerical_tie(cost, lowest_cost)
    ]

    if len(tied_candidates) > 1:
        winner, reason = _resolve_numerical_tie_with_reason(
            tied_candidates
        )
        numerical_tie = True
    else:
        winner = tied_candidates[0]

        losing_candidates = [
            (candidate, cost)
            for candidate, cost in scored_candidates
            if candidate is not winner
        ]
        best_losing_candidate = min(
            losing_candidates,
            key=lambda scored_candidate: scored_candidate[1],
        )[0]

        reason = _determine_standard_decision_reason(
            winner,
            best_losing_candidate,
        )
        numerical_tie = False

    return DecisionResult(
        recommended_route=winner.route,
        reason=reason,
        numerical_tie=numerical_tie,
        missing_data_present=missing_data_present,
        candidate_count=candidate_count,
        eligible_count=eligible_count,
    )