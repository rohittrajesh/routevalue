from decimal import Decimal

import pytest

from routevalue.api.mappers import (
    get_value_of_time_per_hour,
    to_gasoline_vehicle_profile,
    to_route_search_request,
    to_trip_evaluation_response,
    to_user_override_fuel_price_quote,
)
from routevalue.api.schemas import (
    GasolineGradeInput,
    GasolineInputs,
    ResolvedLocationInput,
    TripEvaluationRequest,
)
from routevalue.application.models import (
    ResolvedLocation,
    RouteEvaluation,
    RouteGeometry,
    RoutePoint,
    RouteSearchRequest,
    TripEvaluationResult,
)
from routevalue.domain.models import (
    CostBreakdown,
    DecisionReason,
    DecisionResult,
    EligibilityResult,
    EnergyEstimate,
    FuelPriceSource,
    GasolineGrade,
    GasolineVehicleProfile,
    IneligibilityReason,
    RouteCandidate,
)


def _gasoline_inputs(
    *,
    fuel_grade: GasolineGradeInput = GasolineGradeInput.REGULAR,
) -> GasolineInputs:
    return GasolineInputs(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=fuel_grade,
        fuel_price_per_gallon=Decimal("4.50"),
    )


def _resolved_location_input(
    display_name: str,
    *,
    source_id: str,
) -> ResolvedLocationInput:
    return ResolvedLocationInput(
        display_name=display_name,
        latitude=32.88,
        longitude=-117.23,
        source="google_places",
        source_id=source_id,
    )


def _trip_evaluation_request(
    *,
    value_of_time_per_hour: Decimal = Decimal("18.00"),
    gasoline: GasolineInputs | None = None,
) -> TripEvaluationRequest:
    return TripEvaluationRequest(
        origin=_resolved_location_input(
            "Origin",
            source_id="origin-place-id",
        ),
        destination=_resolved_location_input(
            "Destination",
            source_id="destination-place-id",
        ),
        value_of_time_per_hour=value_of_time_per_hour,
        gasoline=gasoline if gasoline is not None else _gasoline_inputs(),
    )


def test_to_route_search_request_maps_api_request_to_application_model() -> None:
    api_request = _trip_evaluation_request()

    result = to_route_search_request(api_request)

    assert result == RouteSearchRequest(
        origin=ResolvedLocation(
            display_name="Origin",
            latitude=32.88,
            longitude=-117.23,
            source="google_places",
            source_id="origin-place-id",
        ),
        destination=ResolvedLocation(
            display_name="Destination",
            latitude=32.88,
            longitude=-117.23,
            source="google_places",
            source_id="destination-place-id",
        ),
    )


def test_to_route_search_request_preserves_location_coordinates() -> None:
    api_request = TripEvaluationRequest(
        origin=ResolvedLocationInput(
            display_name="Origin",
            latitude=33.123456,
            longitude=-117.654321,
        ),
        destination=ResolvedLocationInput(
            display_name="Destination",
            latitude=32.987654,
            longitude=-117.123456,
        ),
        value_of_time_per_hour=Decimal("18.00"),
        gasoline=_gasoline_inputs(),
    )

    result = to_route_search_request(api_request)

    assert result.origin.latitude == 33.123456
    assert result.origin.longitude == -117.654321
    assert result.destination.latitude == 32.987654
    assert result.destination.longitude == -117.123456


def test_get_value_of_time_per_hour_preserves_decimal_value() -> None:
    api_request = _trip_evaluation_request(
        value_of_time_per_hour=Decimal("18.75"),
    )

    result = get_value_of_time_per_hour(api_request)

    assert result == Decimal("18.75")


def test_to_gasoline_vehicle_profile_maps_api_request() -> None:
    api_request = _trip_evaluation_request()

    result = to_gasoline_vehicle_profile(api_request)

    assert result == GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )


def test_to_user_override_fuel_price_quote_maps_api_request() -> None:
    api_request = _trip_evaluation_request()

    result = to_user_override_fuel_price_quote(api_request)

    assert result.price_per_gallon == Decimal("4.50")
    assert result.fuel_grade is GasolineGrade.REGULAR
    assert result.source is FuelPriceSource.USER_OVERRIDE
    assert result.observed_at is None


@pytest.mark.parametrize(
    ("api_grade", "domain_grade"),
    [
        (GasolineGradeInput.REGULAR, GasolineGrade.REGULAR),
        (GasolineGradeInput.MIDGRADE, GasolineGrade.MIDGRADE),
        (GasolineGradeInput.PREMIUM, GasolineGrade.PREMIUM),
    ],
)
def test_gasoline_grade_mapping_supports_all_v1_grades(
    api_grade: GasolineGradeInput,
    domain_grade: GasolineGrade,
) -> None:
    request = _trip_evaluation_request(
        gasoline=_gasoline_inputs(fuel_grade=api_grade),
    )

    vehicle = to_gasoline_vehicle_profile(request)
    quote = to_user_override_fuel_price_quote(request)

    assert vehicle.fuel_grade is domain_grade
    assert quote.fuel_grade is domain_grade


def test_to_trip_evaluation_response_maps_eligible_route() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("1.50"),
    )
    energy_estimate = EnergyEstimate(cost=Decimal("2.25"))
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

    result = TripEvaluationResult(
        route_evaluations=(
            RouteEvaluation(
                route=route,
                energy_estimate=energy_estimate,
                eligibility=EligibilityResult(
                    eligible=True,
                    reason=None,
                ),
                cost_breakdown=CostBreakdown(
                    monetary_cost=Decimal("3.75"),
                    time_cost=Decimal("4.50"),
                    generalized_cost=Decimal("8.25"),
                ),
                geometry=geometry,
            ),
        ),
        decision=DecisionResult(
            recommended_route=route,
            reason=DecisionReason.ONLY_ELIGIBLE_ROUTE,
            numerical_tie=False,
            missing_data_present=False,
            candidate_count=1,
            eligible_count=1,
        ),
    )

    response = to_trip_evaluation_response(result)

    assert len(response.route_evaluations) == 1

    evaluation = response.route_evaluations[0]

    assert evaluation.route.distance_meters == 10_000
    assert evaluation.route.duration_seconds == 900
    assert evaluation.route.toll_cost == Decimal("1.50")
    assert evaluation.energy_estimate is not None
    assert evaluation.energy_estimate.cost == Decimal("2.25")
    assert evaluation.eligibility.eligible
    assert evaluation.eligibility.reason is None
    assert evaluation.cost_breakdown is not None
    assert evaluation.cost_breakdown.monetary_cost == Decimal("3.75")
    assert evaluation.cost_breakdown.time_cost == Decimal("4.50")
    assert evaluation.cost_breakdown.generalized_cost == Decimal("8.25")

    assert evaluation.geometry is not None
    assert [(point.latitude, point.longitude) for point in evaluation.geometry.points] == [
        (32.8801, -117.2340),
        (32.7338, -117.1933),
    ]

    assert response.decision.recommended_route is not None
    assert response.decision.recommended_route.distance_meters == 10_000
    assert response.decision.reason == "only_eligible_route"
    assert response.decision.candidate_count == 1
    assert response.decision.eligible_count == 1


def test_to_trip_evaluation_response_preserves_missing_data() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )

    result = TripEvaluationResult(
        route_evaluations=(
            RouteEvaluation(
                route=route,
                energy_estimate=None,
                eligibility=EligibilityResult(
                    eligible=False,
                    reason=IneligibilityReason.MISSING_TOLL_COST,
                ),
                cost_breakdown=None,
            ),
        ),
        decision=DecisionResult(
            recommended_route=None,
            reason=None,
            numerical_tie=False,
            missing_data_present=True,
            candidate_count=1,
            eligible_count=0,
        ),
    )

    response = to_trip_evaluation_response(result)

    evaluation = response.route_evaluations[0]

    assert evaluation.route.toll_cost is None
    assert evaluation.energy_estimate is None
    assert not evaluation.eligibility.eligible
    assert evaluation.eligibility.reason == "missing_toll_cost"

    assert response.decision.recommended_route is None
    assert response.decision.reason is None
    assert response.decision.missing_data_present
    assert evaluation.cost_breakdown is None
    assert evaluation.geometry is None


def test_to_trip_evaluation_response_maps_decision_reason_to_string() -> None:
    first_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    second_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("1.00"),
    )

    result = TripEvaluationResult(
        route_evaluations=(
            RouteEvaluation(
                route=first_route,
                energy_estimate=EnergyEstimate(cost=Decimal("2.00")),
                eligibility=EligibilityResult(
                    eligible=True,
                    reason=None,
                ),
                cost_breakdown=CostBreakdown(
                    monetary_cost=Decimal("2.00"),
                    time_cost=Decimal("4.50"),
                    generalized_cost=Decimal("6.50"),
                ),
            ),
            RouteEvaluation(
                route=second_route,
                energy_estimate=EnergyEstimate(cost=Decimal("1.00")),
                eligibility=EligibilityResult(
                    eligible=True,
                    reason=None,
                ),
                cost_breakdown=CostBreakdown(
                    monetary_cost=Decimal("2.00"),
                    time_cost=Decimal("4.50"),
                    generalized_cost=Decimal("6.50"),
                ),
            ),
        ),
        decision=DecisionResult(
            recommended_route=first_route,
            reason=DecisionReason.NUMERICAL_TIE_STABLE_ORDER_WINS,
            numerical_tie=True,
            missing_data_present=False,
            candidate_count=2,
            eligible_count=2,
        ),
    )

    response = to_trip_evaluation_response(result)

    assert response.decision.reason == "numerical_tie_stable_order_wins"
    assert response.decision.numerical_tie


def test_to_trip_evaluation_response_preserves_zero_monetary_values() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    result = TripEvaluationResult(
        route_evaluations=(
            RouteEvaluation(
                route=route,
                energy_estimate=EnergyEstimate(cost=Decimal(0)),
                eligibility=EligibilityResult(
                    eligible=True,
                    reason=None,
                ),
                cost_breakdown=CostBreakdown(
                    monetary_cost=Decimal(0),
                    time_cost=Decimal("4.50"),
                    generalized_cost=Decimal("4.50"),
                ),
            ),
        ),
        decision=DecisionResult(
            recommended_route=route,
            reason=DecisionReason.ONLY_ELIGIBLE_ROUTE,
            numerical_tie=False,
            missing_data_present=False,
            candidate_count=1,
            eligible_count=1,
        ),
    )

    response = to_trip_evaluation_response(result)

    evaluation = response.route_evaluations[0]

    assert evaluation.route.toll_cost == Decimal(0)
    assert evaluation.energy_estimate is not None
    assert evaluation.energy_estimate.cost == Decimal(0)
    assert evaluation.cost_breakdown is not None
    assert evaluation.cost_breakdown.monetary_cost == Decimal(0)
    assert evaluation.cost_breakdown.time_cost == Decimal("4.50")
    assert evaluation.cost_breakdown.generalized_cost == Decimal("4.50")
