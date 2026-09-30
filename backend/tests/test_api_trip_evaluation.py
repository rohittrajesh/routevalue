from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from routevalue.api.dependencies import get_trip_evaluation_orchestrator
from routevalue.application.trip_evaluation import TripEvaluationOrchestrator
from routevalue.domain.models import EnergyEstimate, RouteCandidate
from routevalue.infrastructure.in_memory import (
    InMemoryEnergyCostEstimator,
    InMemoryRouteProvider,
)
from routevalue.main import app


def test_trip_evaluation_endpoint_returns_application_result() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("1.50"),
    )
    estimate = EnergyEstimate(
        cost=Decimal("2.25"),
    )

    def override_trip_evaluation_orchestrator() -> TripEvaluationOrchestrator:
        return TripEvaluationOrchestrator(
            route_provider=InMemoryRouteProvider((route,)),
            energy_cost_estimator=InMemoryEnergyCostEstimator(
                {
                    route: estimate,
                }
            ),
        )

    app.dependency_overrides[get_trip_evaluation_orchestrator] = (
        override_trip_evaluation_orchestrator
    )

    try:
        client = TestClient(app)

        response = client.post(
            "/trip-evaluations",
            json={
                "origin": "Origin",
                "destination": "Destination",
                "value_of_time_per_hour": "18.00",
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["route_evaluations"] == [
            {
                "route": {
                    "distance_meters": 10_000,
                    "duration_seconds": 900,
                    "toll_cost": "1.50",
                },
                "energy_estimate": {
                    "cost": "2.25",
                },
                "eligibility": {
                    "eligible": True,
                    "reason": None,
                },
            }
        ]

        assert body["decision"] == {
            "recommended_route": {
                "distance_meters": 10_000,
                "duration_seconds": 900,
                "toll_cost": "1.50",
            },
            "reason": "only_eligible_route",
            "numerical_tie": False,
            "missing_data_present": False,
            "candidate_count": 1,
            "eligible_count": 1,
        }
    finally:
        app.dependency_overrides.clear()


def test_trip_evaluation_endpoint_handles_zero_routes() -> None:
    client = TestClient(app)

    response = client.post(
        "/trip-evaluations",
        json={
            "origin": "Origin",
            "destination": "Destination",
            "value_of_time_per_hour": "18.00",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "route_evaluations": [],
        "decision": {
            "recommended_route": None,
            "reason": None,
            "numerical_tie": False,
            "missing_data_present": False,
            "candidate_count": 0,
            "eligible_count": 0,
        },
    }


def test_trip_evaluation_endpoint_preserves_missing_toll_cost() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )
    estimate = EnergyEstimate(
        cost=Decimal("2.25"),
    )

    def override_trip_evaluation_orchestrator() -> TripEvaluationOrchestrator:
        return TripEvaluationOrchestrator(
            route_provider=InMemoryRouteProvider((route,)),
            energy_cost_estimator=InMemoryEnergyCostEstimator(
                {
                    route: estimate,
                }
            ),
        )

    app.dependency_overrides[get_trip_evaluation_orchestrator] = (
        override_trip_evaluation_orchestrator
    )

    try:
        client = TestClient(app)

        response = client.post(
            "/trip-evaluations",
            json={
                "origin": "Origin",
                "destination": "Destination",
                "value_of_time_per_hour": "18.00",
            },
        )

        assert response.status_code == 200

        body = response.json()
        evaluation = body["route_evaluations"][0]

        assert evaluation["route"]["toll_cost"] is None
        assert evaluation["energy_estimate"]["cost"] == "2.25"
        assert evaluation["eligibility"] == {
            "eligible": False,
            "reason": "missing_toll_cost",
        }

        assert body["decision"]["recommended_route"] is None
        assert body["decision"]["reason"] is None
        assert body["decision"]["missing_data_present"] is True
        assert body["decision"]["candidate_count"] == 1
        assert body["decision"]["eligible_count"] == 0
    finally:
        app.dependency_overrides.clear()


def test_trip_evaluation_endpoint_preserves_missing_energy_estimate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )

    def override_trip_evaluation_orchestrator() -> TripEvaluationOrchestrator:
        return TripEvaluationOrchestrator(
            route_provider=InMemoryRouteProvider((route,)),
            energy_cost_estimator=InMemoryEnergyCostEstimator(
                {
                    route: None,
                }
            ),
        )

    app.dependency_overrides[get_trip_evaluation_orchestrator] = (
        override_trip_evaluation_orchestrator
    )

    try:
        client = TestClient(app)

        response = client.post(
            "/trip-evaluations",
            json={
                "origin": "Origin",
                "destination": "Destination",
                "value_of_time_per_hour": "18.00",
            },
        )

        assert response.status_code == 200

        body = response.json()
        evaluation = body["route_evaluations"][0]

        assert evaluation["energy_estimate"] is None
        assert evaluation["eligibility"] == {
            "eligible": False,
            "reason": "missing_energy_estimate",
        }

        assert body["decision"]["recommended_route"] is None
        assert body["decision"]["missing_data_present"] is True
        assert body["decision"]["eligible_count"] == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "destination": "Destination",
            "value_of_time_per_hour": "18.00",
        },
        {
            "origin": "   ",
            "destination": "Destination",
            "value_of_time_per_hour": "18.00",
        },
        {
            "origin": "Origin",
            "destination": "   ",
            "value_of_time_per_hour": "18.00",
        },
        {
            "origin": "Origin",
            "destination": "Destination",
            "value_of_time_per_hour": "-0.01",
        },
    ],
)
def test_trip_evaluation_endpoint_rejects_invalid_request(
    payload: dict[str, object],
) -> None:
    client = TestClient(app)

    response = client.post(
        "/trip-evaluations",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["detail"]
