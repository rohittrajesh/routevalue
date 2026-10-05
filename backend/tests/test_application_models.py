from decimal import Decimal

import pytest

from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteEvaluation,
    RouteGeometry,
    RoutePoint,
    TripEvaluationResult,
)
from routevalue.domain.models import (
    CostBreakdown,
    DecisionReason,
    DecisionResult,
    EligibilityResult,
    EnergyEstimate,
    IneligibilityReason,
    RouteCandidate,
)


def test_resolved_location_preserves_normalized_location_data() -> None:
    location = ResolvedLocation(
        display_name="UC San Diego",
        latitude=32.8801,
        longitude=-117.2340,
        source="google_places",
        source_id="test-place-id",
    )

    assert location.display_name == "UC San Diego"
    assert location.latitude == 32.8801
    assert location.longitude == -117.2340
    assert location.source == "google_places"
    assert location.source_id == "test-place-id"


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (-90.01, 0),
        (90.01, 0),
        (0, -180.01),
        (0, 180.01),
    ],
)
def test_resolved_location_rejects_invalid_coordinates(
    latitude: float,
    longitude: float,
) -> None:
    with pytest.raises(ValueError):
        ResolvedLocation(
            display_name="Location",
            latitude=latitude,
            longitude=longitude,
        )


@pytest.mark.parametrize(
    ("source", "source_id"),
    [
        ("google_places", None),
        (None, "place-id"),
        ("", "place-id"),
        ("google_places", ""),
    ],
)
def test_resolved_location_rejects_invalid_external_reference(
    source: str | None,
    source_id: str | None,
) -> None:
    with pytest.raises(ValueError):
        ResolvedLocation(
            display_name="Location",
            latitude=32.88,
            longitude=-117.23,
            source=source,
            source_id=source_id,
        )


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (-90.0, -180.0),
        (-90.0, 180.0),
        (90.0, -180.0),
        (90.0, 180.0),
        (0.0, 0.0),
    ],
)
def test_route_point_accepts_valid_coordinate_boundaries(
    latitude: float,
    longitude: float,
) -> None:
    point = RoutePoint(
        latitude=latitude,
        longitude=longitude,
    )

    assert point.latitude == latitude
    assert point.longitude == longitude


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (-90.01, 0.0),
        (90.01, 0.0),
        (0.0, -180.01),
        (0.0, 180.01),
    ],
)
def test_route_point_rejects_invalid_coordinates(
    latitude: float,
    longitude: float,
) -> None:
    with pytest.raises(ValueError):
        RoutePoint(
            latitude=latitude,
            longitude=longitude,
        )


def test_route_geometry_preserves_point_order() -> None:
    first_point = RoutePoint(
        latitude=32.8801,
        longitude=-117.2340,
    )
    second_point = RoutePoint(
        latitude=32.8500,
        longitude=-117.2200,
    )
    third_point = RoutePoint(
        latitude=32.7338,
        longitude=-117.1933,
    )

    geometry = RouteGeometry(
        points=(
            first_point,
            second_point,
            third_point,
        )
    )

    assert geometry.points == (
        first_point,
        second_point,
        third_point,
    )


@pytest.mark.parametrize(
    "points",
    [
        (),
        (
            RoutePoint(
                latitude=32.8801,
                longitude=-117.2340,
            ),
        ),
    ],
)
def test_route_geometry_requires_at_least_two_points(
    points: tuple[RoutePoint, ...],
) -> None:
    with pytest.raises(
        ValueError,
        match="route geometry requires at least two points",
    ):
        RouteGeometry(points=points)


def test_provided_route_associates_geometry_with_route_candidate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    geometry = RouteGeometry(
        points=(
            RoutePoint(
                latitude=32.8801,
                longitude=-117.2340,
            ),
            RoutePoint(
                latitude=32.7338,
                longitude=-117.1933,
            ),
        )
    )

    provided_route = ProvidedRoute(
        route=route,
        geometry=geometry,
    )

    assert provided_route.route == route
    assert provided_route.geometry == geometry


def test_provided_route_allows_missing_geometry() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    provided_route = ProvidedRoute(route=route)

    assert provided_route.route == route
    assert provided_route.geometry is None


def test_geometry_does_not_change_route_candidate_equality() -> None:
    first_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    second_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    first_provided_route = ProvidedRoute(
        route=first_route,
        geometry=RouteGeometry(
            points=(
                RoutePoint(latitude=32.88, longitude=-117.23),
                RoutePoint(latitude=32.73, longitude=-117.19),
            )
        ),
    )
    second_provided_route = ProvidedRoute(
        route=second_route,
        geometry=RouteGeometry(
            points=(
                RoutePoint(latitude=32.88, longitude=-117.23),
                RoutePoint(latitude=32.80, longitude=-117.20),
                RoutePoint(latitude=32.73, longitude=-117.19),
            )
        ),
    )

    assert first_provided_route.route == second_provided_route.route
    assert first_provided_route.geometry != second_provided_route.geometry


def test_trip_evaluation_result_preserves_route_evaluations_and_decision() -> None:
    eligible_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    ineligible_route = RouteCandidate(
        distance_meters=12_000,
        duration_seconds=1_000,
        toll_cost=None,
    )

    eligible_evaluation = RouteEvaluation(
        route=eligible_route,
        energy_estimate=EnergyEstimate(cost=Decimal("1.25")),
        eligibility=EligibilityResult(
            eligible=True,
            reason=None,
        ),
        cost_breakdown=CostBreakdown(
            monetary_cost=Decimal("1.25"),
            time_cost=Decimal("4.50"),
            generalized_cost=Decimal("5.75"),
        ),
    )

    ineligible_evaluation = RouteEvaluation(
        route=ineligible_route,
        energy_estimate=EnergyEstimate(cost=Decimal("1.50")),
        eligibility=EligibilityResult(
            eligible=False,
            reason=IneligibilityReason.MISSING_TOLL_COST,
        ),
        cost_breakdown=None,
    )

    decision = DecisionResult(
        recommended_route=eligible_route,
        reason=DecisionReason.ONLY_ELIGIBLE_ROUTE,
        numerical_tie=False,
        missing_data_present=True,
        candidate_count=2,
        eligible_count=1,
    )

    result = TripEvaluationResult(
        route_evaluations=(
            eligible_evaluation,
            ineligible_evaluation,
        ),
        decision=decision,
    )

    assert result.route_evaluations == (
        eligible_evaluation,
        ineligible_evaluation,
    )
    assert result.decision == decision


def test_trip_evaluation_result_rejects_candidate_count_mismatch() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    evaluation = RouteEvaluation(
        route=route,
        energy_estimate=EnergyEstimate(cost=Decimal("1.25")),
        eligibility=EligibilityResult(
            eligible=True,
            reason=None,
        ),
        cost_breakdown=CostBreakdown(
            monetary_cost=Decimal("1.25"),
            time_cost=Decimal("4.50"),
            generalized_cost=Decimal("5.75"),
        ),
    )
    decision = DecisionResult(
        recommended_route=route,
        reason=DecisionReason.ONLY_ELIGIBLE_ROUTE,
        numerical_tie=False,
        missing_data_present=False,
        candidate_count=2,
        eligible_count=1,
    )

    with pytest.raises(
        ValueError,
        match="route evaluation count must match decision candidate count",
    ):
        TripEvaluationResult(
            route_evaluations=(evaluation,),
            decision=decision,
        )


def test_trip_evaluation_result_rejects_eligible_count_mismatch() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    evaluation = RouteEvaluation(
        route=route,
        energy_estimate=EnergyEstimate(cost=Decimal("1.25")),
        eligibility=EligibilityResult(
            eligible=True,
            reason=None,
        ),
        cost_breakdown=CostBreakdown(
            monetary_cost=Decimal("1.25"),
            time_cost=Decimal("4.50"),
            generalized_cost=Decimal("5.75"),
        ),
    )
    decision = DecisionResult(
        recommended_route=None,
        reason=None,
        numerical_tie=False,
        missing_data_present=False,
        candidate_count=1,
        eligible_count=0,
    )

    with pytest.raises(
        ValueError,
        match="eligible route evaluation count must match decision eligible count",
    ):
        TripEvaluationResult(
            route_evaluations=(evaluation,),
            decision=decision,
        )


def test_trip_evaluation_result_rejects_missing_data_mismatch() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )
    evaluation = RouteEvaluation(
        route=route,
        energy_estimate=EnergyEstimate(cost=Decimal("1.25")),
        eligibility=EligibilityResult(
            eligible=False,
            reason=IneligibilityReason.MISSING_TOLL_COST,
        ),
        cost_breakdown=None,
    )
    decision = DecisionResult(
        recommended_route=None,
        reason=None,
        numerical_tie=False,
        missing_data_present=False,
        candidate_count=1,
        eligible_count=0,
    )

    with pytest.raises(
        ValueError,
        match="route evaluation missing-data state must match decision",
    ):
        TripEvaluationResult(
            route_evaluations=(evaluation,),
            decision=decision,
        )
