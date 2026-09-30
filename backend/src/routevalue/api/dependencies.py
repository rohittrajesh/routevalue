"""Dependency composition for the RouteValue API."""

from routevalue.application.ports import EnergyCostEstimator, RouteProvider
from routevalue.application.trip_evaluation import TripEvaluationOrchestrator
from routevalue.infrastructure.in_memory import (
    InMemoryEnergyCostEstimator,
    InMemoryRouteProvider,
)


def get_trip_evaluation_orchestrator() -> TripEvaluationOrchestrator:
    """Build the temporary orchestrator used by the HTTP API."""

    route_provider: RouteProvider = InMemoryRouteProvider(())
    energy_cost_estimator: EnergyCostEstimator = InMemoryEnergyCostEstimator({})

    return TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_cost_estimator,
    )
