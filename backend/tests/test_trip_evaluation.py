from collections.abc import Sequence
from decimal import Decimal

from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteGeometry,
    RoutePoint,
    RouteSearchRequest,
)
from routevalue.application.ports import EnergyCostEstimator, RouteProvider
from routevalue.application.trip_evaluation import TripEvaluationOrchestrator
from routevalue.domain.models import (
    DecisionReason,
    EnergyEstimate,
    IneligibilityReason,
    RouteCandidate,
)


class FakeRouteProvider:
    def __init__(
        self,
        routes: Sequence[RouteCandidate | ProvidedRoute],
    ) -> None:
        self._routes = tuple(
            route if isinstance(route, ProvidedRoute) else ProvidedRoute(route=route)
            for route in routes
        )
        self.requests: list[RouteSearchRequest] = []

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        self.requests.append(request)
        return self._routes


class FakeEnergyCostEstimator:
    def __init__(
        self,
        estimates: dict[RouteCandidate, EnergyEstimate | None],
    ) -> None:
        self._estimates = estimates
        self.routes: list[RouteCandidate] = []

    def estimate_energy(
        self,
        route: RouteCandidate,
    ) -> EnergyEstimate | None:
        self.routes.append(route)
        return self._estimates[route]


def _route_search_request() -> RouteSearchRequest:
    return RouteSearchRequest(
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


def test_evaluate_trip_coordinates_happy_path() -> None:
    first_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_200,
        toll_cost=Decimal(0),
    )
    second_route = RouteCandidate(
        distance_meters=12_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    request = _route_search_request()

    route_provider: RouteProvider = FakeRouteProvider([first_route, second_route])
    energy_estimator: EnergyCostEstimator = FakeEnergyCostEstimator(
        {
            first_route: EnergyEstimate(cost=Decimal("2.00")),
            second_route: EnergyEstimate(cost=Decimal("3.00")),
        }
    )

    orchestrator = TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_estimator,
    )

    result = orchestrator.evaluate_trip(
        request,
        value_of_time_per_hour=Decimal("18.00"),
    )

    assert tuple(evaluation.route for evaluation in result.route_evaluations) == (
        first_route,
        second_route,
    )
    assert all(evaluation.eligibility.eligible for evaluation in result.route_evaluations)

    assert result.decision.recommended_route == second_route
    assert result.decision.reason is DecisionReason.FASTER_ROUTE_WORTH_EXTRA_COST
    assert result.decision.candidate_count == 2
    assert result.decision.eligible_count == 2
    assert not result.decision.missing_data_present


def test_evaluate_trip_preserves_geometry_without_affecting_decision_logic() -> None:
    first_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_200,
        toll_cost=Decimal(0),
    )
    second_route = RouteCandidate(
        distance_meters=12_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    first_geometry = RouteGeometry(
        points=(
            RoutePoint(
                latitude=32.8801,
                longitude=-117.2340,
            ),
            RoutePoint(
                latitude=32.8200,
                longitude=-117.2200,
            ),
            RoutePoint(
                latitude=32.7338,
                longitude=-117.1933,
            ),
        )
    )
    second_geometry = RouteGeometry(
        points=(
            RoutePoint(
                latitude=32.8801,
                longitude=-117.2340,
            ),
            RoutePoint(
                latitude=32.7900,
                longitude=-117.2050,
            ),
            RoutePoint(
                latitude=32.7338,
                longitude=-117.1933,
            ),
        )
    )

    request = _route_search_request()

    route_provider = FakeRouteProvider(
        [
            ProvidedRoute(
                route=first_route,
                geometry=first_geometry,
            ),
            ProvidedRoute(
                route=second_route,
                geometry=second_geometry,
            ),
        ]
    )
    energy_estimator = FakeEnergyCostEstimator(
        {
            first_route: EnergyEstimate(cost=Decimal("2.00")),
            second_route: EnergyEstimate(cost=Decimal("3.00")),
        }
    )

    orchestrator = TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_estimator,
    )

    result = orchestrator.evaluate_trip(
        request,
        value_of_time_per_hour=Decimal("18.00"),
    )

    assert result.route_evaluations[0].route == first_route
    assert result.route_evaluations[0].geometry == first_geometry

    assert result.route_evaluations[1].route == second_route
    assert result.route_evaluations[1].geometry == second_geometry

    assert result.decision.recommended_route == second_route
    assert result.decision.reason is DecisionReason.FASTER_ROUTE_WORTH_EXTRA_COST

    assert energy_estimator.routes == [
        first_route,
        second_route,
    ]


def test_evaluate_trip_handles_no_routes() -> None:
    request = _route_search_request()

    route_provider = FakeRouteProvider([])
    energy_estimator = FakeEnergyCostEstimator({})

    orchestrator = TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_estimator,
    )

    result = orchestrator.evaluate_trip(
        request,
        value_of_time_per_hour=Decimal("18.00"),
    )

    assert result.route_evaluations == ()

    assert result.decision.recommended_route is None
    assert result.decision.reason is None
    assert result.decision.candidate_count == 0
    assert result.decision.eligible_count == 0
    assert not result.decision.numerical_tie
    assert not result.decision.missing_data_present

    assert route_provider.requests == [request]
    assert energy_estimator.routes == []


def test_evaluate_trip_handles_one_eligible_route() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    energy_estimate = EnergyEstimate(
        cost=Decimal("2.00"),
    )

    request = _route_search_request()

    route_provider = FakeRouteProvider([route])
    energy_estimator = FakeEnergyCostEstimator(
        {
            route: energy_estimate,
        }
    )

    orchestrator = TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_estimator,
    )

    result = orchestrator.evaluate_trip(
        request,
        value_of_time_per_hour=Decimal("18.00"),
    )

    assert len(result.route_evaluations) == 1

    evaluation = result.route_evaluations[0]

    assert evaluation.route == route
    assert evaluation.geometry is None
    assert evaluation.energy_estimate == energy_estimate
    assert evaluation.eligibility.eligible
    assert evaluation.eligibility.reason is None

    assert result.decision.recommended_route == route
    assert result.decision.reason is DecisionReason.ONLY_ELIGIBLE_ROUTE
    assert result.decision.candidate_count == 1
    assert result.decision.eligible_count == 1
    assert not result.decision.numerical_tie
    assert not result.decision.missing_data_present

    assert route_provider.requests == [request]
    assert energy_estimator.routes == [route]


def test_evaluate_trip_excludes_route_with_missing_toll_cost() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )
    energy_estimate = EnergyEstimate(
        cost=Decimal("2.00"),
    )

    request = _route_search_request()

    route_provider = FakeRouteProvider([route])
    energy_estimator = FakeEnergyCostEstimator(
        {
            route: energy_estimate,
        }
    )

    orchestrator = TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_estimator,
    )

    result = orchestrator.evaluate_trip(
        request,
        value_of_time_per_hour=Decimal("18.00"),
    )

    evaluation = result.route_evaluations[0]

    assert evaluation.route == route
    assert evaluation.energy_estimate == energy_estimate
    assert not evaluation.eligibility.eligible
    assert evaluation.eligibility.reason is IneligibilityReason.MISSING_TOLL_COST

    assert result.decision.recommended_route is None
    assert result.decision.reason is None
    assert result.decision.candidate_count == 1
    assert result.decision.eligible_count == 0
    assert result.decision.missing_data_present


def test_evaluate_trip_excludes_route_with_missing_energy_estimate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    request = _route_search_request()

    route_provider = FakeRouteProvider([route])
    energy_estimator = FakeEnergyCostEstimator(
        {
            route: None,
        }
    )

    orchestrator = TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_estimator,
    )

    result = orchestrator.evaluate_trip(
        request,
        value_of_time_per_hour=Decimal("18.00"),
    )

    evaluation = result.route_evaluations[0]

    assert evaluation.route == route
    assert evaluation.energy_estimate is None
    assert not evaluation.eligibility.eligible
    assert evaluation.eligibility.reason is IneligibilityReason.MISSING_ENERGY_ESTIMATE

    assert result.decision.recommended_route is None
    assert result.decision.reason is None
    assert result.decision.candidate_count == 1
    assert result.decision.eligible_count == 0
    assert result.decision.missing_data_present


def test_evaluate_trip_optimizes_only_eligible_routes() -> None:
    eligible_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    ineligible_route = RouteCandidate(
        distance_meters=8_000,
        duration_seconds=700,
        toll_cost=None,
    )

    request = _route_search_request()

    route_provider = FakeRouteProvider(
        [
            ineligible_route,
            eligible_route,
        ]
    )
    energy_estimator = FakeEnergyCostEstimator(
        {
            ineligible_route: EnergyEstimate(cost=Decimal("1.00")),
            eligible_route: EnergyEstimate(cost=Decimal("2.00")),
        }
    )

    orchestrator = TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_estimator,
    )

    result = orchestrator.evaluate_trip(
        request,
        value_of_time_per_hour=Decimal("18.00"),
    )

    assert tuple(evaluation.route for evaluation in result.route_evaluations) == (
        ineligible_route,
        eligible_route,
    )

    assert not result.route_evaluations[0].eligibility.eligible
    assert result.route_evaluations[0].eligibility.reason is IneligibilityReason.MISSING_TOLL_COST
    assert result.route_evaluations[1].eligibility.eligible

    assert result.decision.recommended_route == eligible_route
    assert result.decision.reason is DecisionReason.ONLY_ELIGIBLE_ROUTE
    assert result.decision.candidate_count == 2
    assert result.decision.eligible_count == 1
    assert result.decision.missing_data_present


def test_evaluate_trip_treats_zero_monetary_values_as_known_data() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    energy_estimate = EnergyEstimate(
        cost=Decimal(0),
    )

    request = _route_search_request()

    route_provider = FakeRouteProvider([route])
    energy_estimator = FakeEnergyCostEstimator(
        {
            route: energy_estimate,
        }
    )

    orchestrator = TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_estimator,
    )

    result = orchestrator.evaluate_trip(
        request,
        value_of_time_per_hour=Decimal("18.00"),
    )

    evaluation = result.route_evaluations[0]

    assert evaluation.route.toll_cost == Decimal(0)
    assert evaluation.energy_estimate == energy_estimate
    assert evaluation.eligibility.eligible
    assert evaluation.eligibility.reason is None

    assert result.decision.recommended_route == route
    assert result.decision.reason is DecisionReason.ONLY_ELIGIBLE_ROUTE
    assert result.decision.candidate_count == 1
    assert result.decision.eligible_count == 1
    assert not result.decision.missing_data_present


def test_evaluate_trip_preserves_provider_order_for_final_tie_break() -> None:
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

    request = _route_search_request()

    route_provider = FakeRouteProvider(
        [
            first_route,
            second_route,
        ]
    )
    energy_estimator = FakeEnergyCostEstimator(
        {
            first_route: EnergyEstimate(cost=Decimal("2.00")),
            second_route: EnergyEstimate(cost=Decimal("1.00")),
        }
    )

    orchestrator = TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_estimator,
    )

    result = orchestrator.evaluate_trip(
        request,
        value_of_time_per_hour=Decimal("18.00"),
    )

    assert tuple(evaluation.route for evaluation in result.route_evaluations) == (
        first_route,
        second_route,
    )

    assert result.decision.recommended_route == first_route
    assert result.decision.reason is DecisionReason.NUMERICAL_TIE_STABLE_ORDER_WINS
    assert result.decision.numerical_tie
    assert result.decision.candidate_count == 2
    assert result.decision.eligible_count == 2
    assert not result.decision.missing_data_present

    assert route_provider.requests == [request]
    assert energy_estimator.routes == [
        first_route,
        second_route,
    ]


def test_evaluate_trip_preserves_primary_reason_when_multiple_data_are_missing() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )

    request = _route_search_request()

    route_provider = FakeRouteProvider([route])
    energy_estimator = FakeEnergyCostEstimator(
        {
            route: None,
        }
    )

    orchestrator = TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_estimator,
    )

    result = orchestrator.evaluate_trip(
        request,
        value_of_time_per_hour=Decimal("18.00"),
    )

    evaluation = result.route_evaluations[0]

    assert evaluation.energy_estimate is None
    assert not evaluation.eligibility.eligible
    assert evaluation.eligibility.reason is IneligibilityReason.MISSING_TOLL_COST

    assert result.decision.recommended_route is None
    assert result.decision.eligible_count == 0
    assert result.decision.missing_data_present
