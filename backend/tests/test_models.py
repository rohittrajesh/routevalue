from decimal import Decimal

import pytest

from routevalue.domain.models import (
    DecisionCandidate,
    DecisionReason,
    DecisionResult,
    EligibilityResult,
    EnergyEstimate,
    RouteCandidate,
    VehicleProfile,
)


def test_route_candidate_accepts_valid_values() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("4.50"),
    )

    assert route.distance_meters == 10_000
    assert route.duration_seconds == 900
    assert route.toll_cost == Decimal("4.50")


def test_route_candidate_allows_zero_values() -> None:
    route = RouteCandidate(
        distance_meters=0,
        duration_seconds=0,
        toll_cost=Decimal(0),
    )

    assert route.distance_meters == 0
    assert route.duration_seconds == 0
    assert route.toll_cost == Decimal(0)


def test_route_candidate_rejects_negative_distance() -> None:
    with pytest.raises(ValueError, match="distance_meters cannot be negative"):
        RouteCandidate(
            distance_meters=-1,
            duration_seconds=900,
            toll_cost=Decimal(0),
        )


def test_route_candidate_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="duration_seconds cannot be negative"):
        RouteCandidate(
            distance_meters=10_000,
            duration_seconds=-1,
            toll_cost=Decimal(0),
        )

def test_route_candidate_allows_unknown_toll_cost() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )

    assert route.toll_cost is None


def test_route_candidate_rejects_negative_toll_cost() -> None:
    with pytest.raises(ValueError, match="toll_cost cannot be negative"):
        RouteCandidate(
            distance_meters=10_000,
            duration_seconds=900,
            toll_cost=Decimal("-0.01"),
        )

def test_vehicle_profile_accepts_valid_values() -> None:
    vehicle = VehicleProfile(
        fuel_efficiency_mpg=Decimal("28.5"),
        fuel_price_per_gallon=Decimal("4.75"),
    )

    assert vehicle.fuel_efficiency_mpg == Decimal("28.5")
    assert vehicle.fuel_price_per_gallon == Decimal("4.75")


def test_vehicle_profile_allows_zero_fuel_price() -> None:
    vehicle = VehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_price_per_gallon=Decimal(0),
    )

    assert vehicle.fuel_price_per_gallon == Decimal(0)


def test_vehicle_profile_rejects_zero_fuel_efficiency() -> None:
    with pytest.raises(
        ValueError,
        match="fuel_efficiency_mpg must be greater than zero",
    ):
        VehicleProfile(
            fuel_efficiency_mpg=Decimal(0),
            fuel_price_per_gallon=Decimal("4.75"),
        )


def test_vehicle_profile_rejects_negative_fuel_efficiency() -> None:
    with pytest.raises(
        ValueError,
        match="fuel_efficiency_mpg must be greater than zero",
    ):
        VehicleProfile(
            fuel_efficiency_mpg=Decimal(-1),
            fuel_price_per_gallon=Decimal("4.75"),
        )


def test_vehicle_profile_rejects_negative_fuel_price() -> None:
    with pytest.raises(
        ValueError,
        match="fuel_price_per_gallon cannot be negative",
    ):
        VehicleProfile(
            fuel_efficiency_mpg=Decimal(30),
            fuel_price_per_gallon=Decimal("-0.01"),
        )

def test_energy_estimate_accepts_positive_cost() -> None:
    estimate = EnergyEstimate(cost=Decimal("6.42"))

    assert estimate.cost == Decimal("6.42")


def test_energy_estimate_allows_zero_cost() -> None:
    estimate = EnergyEstimate(cost=Decimal(0))

    assert estimate.cost == Decimal(0)


def test_energy_estimate_rejects_negative_cost() -> None:
    with pytest.raises(ValueError, match="energy cost cannot be negative"):
        EnergyEstimate(cost=Decimal("-0.01"))

def test_eligibility_result_represents_eligible_route() -> None:
    result = EligibilityResult(
        eligible=True,
        reason=None,
    )

    assert result.eligible is True
    assert result.reason is None


def test_eligibility_result_preserves_ineligibility_reason() -> None:
    result = EligibilityResult(
        eligible=False,
        reason="example ineligibility reason",
    )

    assert result.eligible is False
    assert result.reason == "example ineligibility reason"

def test_eligibility_result_rejects_reason_for_eligible_route() -> None:
    with pytest.raises(
        ValueError,
        match="eligible route cannot have an ineligibility reason",
    ):
        EligibilityResult(
            eligible=True,
            reason="should not be here",
        )


def test_eligibility_result_requires_reason_for_ineligible_route() -> None:
    with pytest.raises(
        ValueError,
        match="ineligible route must have an ineligibility reason",
    ):
        EligibilityResult(
            eligible=False,
            reason=None,
        )

def test_decision_result_accepts_valid_recommendation() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    result = DecisionResult(
        recommended_route=route,
        reason=DecisionReason.FASTER_AND_CHEAPER,
        numerical_tie=False,
        missing_data_present=False,
        candidate_count=2,
        eligible_count=2,
    )

    assert result.recommended_route == route
    assert result.reason is DecisionReason.FASTER_AND_CHEAPER
    assert result.candidate_count == 2
    assert result.eligible_count == 2


def test_decision_result_allows_no_recommendation_when_none_are_eligible() -> None:
    result = DecisionResult(
        recommended_route=None,
        reason=None,
        numerical_tie=False,
        missing_data_present=True,
        candidate_count=2,
        eligible_count=0,
    )

    assert result.recommended_route is None
    assert result.reason is None


def test_decision_result_rejects_negative_candidate_count() -> None:
    with pytest.raises(ValueError, match="candidate_count cannot be negative"):
        DecisionResult(
            recommended_route=None,
            reason=None,
            numerical_tie=False,
            missing_data_present=False,
            candidate_count=-1,
            eligible_count=0,
        )


def test_decision_result_rejects_negative_eligible_count() -> None:
    with pytest.raises(ValueError, match="eligible_count cannot be negative"):
        DecisionResult(
            recommended_route=None,
            reason=None,
            numerical_tie=False,
            missing_data_present=False,
            candidate_count=1,
            eligible_count=-1,
        )


def test_decision_result_rejects_eligible_count_above_candidate_count() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    with pytest.raises(ValueError, match="eligible_count cannot exceed candidate_count"):
        DecisionResult(
            recommended_route=route,
            reason=DecisionReason.ONLY_ELIGIBLE_ROUTE,
            numerical_tie=False,
            missing_data_present=False,
            candidate_count=1,
            eligible_count=2,
        )


def test_decision_result_rejects_recommendation_when_none_are_eligible() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    with pytest.raises(
        ValueError,
        match="cannot recommend a route when no routes are eligible",
    ):
        DecisionResult(
            recommended_route=route,
            reason=None,
            numerical_tie=False,
            missing_data_present=True,
            candidate_count=2,
            eligible_count=0,
        )


def test_decision_result_requires_recommendation_when_routes_are_eligible() -> None:
    with pytest.raises(
        ValueError,
        match="recommended_route is required when eligible routes exist",
    ):
        DecisionResult(
            recommended_route=None,
            reason=DecisionReason.ONLY_ELIGIBLE_ROUTE,
            numerical_tie=False,
            missing_data_present=False,
            candidate_count=1,
            eligible_count=1,
        )

def test_decision_result_requires_reason_for_recommendation() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    with pytest.raises(
        ValueError,
        match="recommended route requires a decision reason",
    ):
        DecisionResult(
            recommended_route=route,
            reason=None,
            numerical_tie=False,
            missing_data_present=False,
            candidate_count=1,
            eligible_count=1,
        )


def test_decision_result_rejects_reason_without_recommendation() -> None:
    with pytest.raises(
        ValueError,
        match="decision reason requires a recommended route",
    ):
        DecisionResult(
            recommended_route=None,
            reason=DecisionReason.ONLY_ELIGIBLE_ROUTE,
            numerical_tie=False,
            missing_data_present=True,
            candidate_count=1,
            eligible_count=0,
        )

def test_decision_candidate_pairs_route_with_energy_estimate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("2.50"),
    )
    energy_estimate = EnergyEstimate(cost=Decimal("3.75"))

    candidate = DecisionCandidate(
        route=route,
        energy_estimate=energy_estimate,
    )

    assert candidate.route is route
    assert candidate.energy_estimate is energy_estimate