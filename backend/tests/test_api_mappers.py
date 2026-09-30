from decimal import Decimal

from routevalue.api.mappers import (
    get_value_of_time_per_hour,
    to_route_search_request,
    to_trip_evaluation_response,
)
from routevalue.api.schemas import TripEvaluationRequest
from routevalue.application.models import (
    RouteEvaluation,
    RouteSearchRequest,
    TripEvaluationResult,
)
from routevalue.domain.models import (
    DecisionReason,
    DecisionResult,
    EligibilityResult,
    EnergyEstimate,
    IneligibilityReason,
    RouteCandidate,
)


def test_to_route_search_request_maps_api_request_to_application_model() -> None:
    api_request = TripEvaluationRequest(
        origin="Origin",
        destination="Destination",
        value_of_time_per_hour=Decimal("18.00"),
    )

    result = to_route_search_request(api_request)

    assert result == RouteSearchRequest(
        origin="Origin",
        destination="Destination",
    )


def test_to_route_search_request_preserves_endpoint_strings() -> None:
    api_request = TripEvaluationRequest(
        origin="  Origin  ",
        destination="  Destination  ",
        value_of_time_per_hour=Decimal("18.00"),
    )

    result = to_route_search_request(api_request)

    assert result.origin == "  Origin  "
    assert result.destination == "  Destination  "


def test_get_value_of_time_per_hour_preserves_decimal_value() -> None:
    api_request = TripEvaluationRequest(
        origin="Origin",
        destination="Destination",
        value_of_time_per_hour=Decimal("18.75"),
    )

    result = get_value_of_time_per_hour(api_request)

    assert result == Decimal("18.75")


def test_to_trip_evaluation_response_maps_eligible_route() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("1.50"),
    )
    energy_estimate = EnergyEstimate(cost=Decimal("2.25"))

    result = TripEvaluationResult(
        route_evaluations=(
            RouteEvaluation(
                route=route,
                energy_estimate=energy_estimate,
                eligibility=EligibilityResult(
                    eligible=True,
                    reason=None,
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

    assert len(response.route_evaluations) == 1

    evaluation = response.route_evaluations[0]

    assert evaluation.route.distance_meters == 10_000
    assert evaluation.route.duration_seconds == 900
    assert evaluation.route.toll_cost == Decimal("1.50")
    assert evaluation.energy_estimate is not None
    assert evaluation.energy_estimate.cost == Decimal("2.25")
    assert evaluation.eligibility.eligible
    assert evaluation.eligibility.reason is None

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
            ),
            RouteEvaluation(
                route=second_route,
                energy_estimate=EnergyEstimate(cost=Decimal("1.00")),
                eligibility=EligibilityResult(
                    eligible=True,
                    reason=None,
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
