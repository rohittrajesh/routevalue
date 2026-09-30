from decimal import Decimal

from routevalue.domain.eligibility import (
    build_decision_candidate_if_eligible,
    evaluate_route_eligibility,
)
from routevalue.domain.models import (
    EnergyEstimate,
    IneligibilityReason,
    RouteCandidate,
)


def test_route_is_eligible_when_all_required_data_is_available() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("2.50"),
    )
    energy_estimate = EnergyEstimate(cost=Decimal("3.75"))

    result = evaluate_route_eligibility(
        route,
        energy_estimate=energy_estimate,
    )

    assert result.eligible is True
    assert result.reason is None


def test_route_with_missing_toll_cost_is_ineligible() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )
    energy_estimate = EnergyEstimate(cost=Decimal("3.75"))

    result = evaluate_route_eligibility(
        route,
        energy_estimate=energy_estimate,
    )

    assert result.eligible is False
    assert result.reason is IneligibilityReason.MISSING_TOLL_COST


def test_route_with_missing_energy_estimate_is_ineligible() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("2.50"),
    )

    result = evaluate_route_eligibility(
        route,
        energy_estimate=None,
    )

    assert result.eligible is False
    assert result.reason is IneligibilityReason.MISSING_ENERGY_ESTIMATE


def test_missing_toll_takes_precedence_when_both_required_values_are_missing() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )

    result = evaluate_route_eligibility(
        route,
        energy_estimate=None,
    )

    assert result.eligible is False
    assert result.reason is IneligibilityReason.MISSING_TOLL_COST


def test_zero_toll_cost_is_known_data_and_remains_eligible() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    energy_estimate = EnergyEstimate(cost=Decimal("3.75"))

    result = evaluate_route_eligibility(
        route,
        energy_estimate=energy_estimate,
    )

    assert result.eligible is True
    assert result.reason is None


def test_zero_energy_cost_is_known_data_and_remains_eligible() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("2.50"),
    )
    energy_estimate = EnergyEstimate(cost=Decimal(0))

    result = evaluate_route_eligibility(
        route,
        energy_estimate=energy_estimate,
    )

    assert result.eligible is True
    assert result.reason is None


def test_eligible_route_builds_decision_candidate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("2.50"),
    )
    energy_estimate = EnergyEstimate(cost=Decimal("3.75"))

    candidate = build_decision_candidate_if_eligible(
        route,
        energy_estimate=energy_estimate,
    )

    assert candidate is not None
    assert candidate.route is route
    assert candidate.energy_estimate is energy_estimate


def test_missing_toll_does_not_build_decision_candidate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )
    energy_estimate = EnergyEstimate(cost=Decimal("3.75"))

    candidate = build_decision_candidate_if_eligible(
        route,
        energy_estimate=energy_estimate,
    )

    assert candidate is None


def test_missing_energy_does_not_build_decision_candidate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("2.50"),
    )

    candidate = build_decision_candidate_if_eligible(
        route,
        energy_estimate=None,
    )

    assert candidate is None


def test_zero_costs_still_build_decision_candidate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    energy_estimate = EnergyEstimate(cost=Decimal(0))

    candidate = build_decision_candidate_if_eligible(
        route,
        energy_estimate=energy_estimate,
    )

    assert candidate is not None
    assert candidate.route is route
    assert candidate.energy_estimate is energy_estimate


def test_both_missing_values_do_not_build_decision_candidate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )

    candidate = build_decision_candidate_if_eligible(
        route,
        energy_estimate=None,
    )

    assert candidate is None
