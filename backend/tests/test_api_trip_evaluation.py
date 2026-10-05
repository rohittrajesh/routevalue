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


def _location_payload(
    display_name: str,
    *,
    source_id: str,
) -> dict[str, object]:
    return {
        "display_name": display_name,
        "latitude": 32.88,
        "longitude": -117.23,
        "source": "google_places",
        "source_id": source_id,
    }


def _valid_trip_payload(
    *,
    value_of_time_per_hour: str = "18.00",
) -> dict[str, object]:
    return {
        "origin": _location_payload(
            "Origin",
            source_id="origin-place-id",
        ),
        "destination": _location_payload(
            "Destination",
            source_id="destination-place-id",
        ),
        "value_of_time_per_hour": value_of_time_per_hour,
        "gasoline": {
            "fuel_efficiency_mpg": "30",
            "fuel_grade": "regular",
            "fuel_price_per_gallon": "4.50",
        },
    }


def _build_empty_trip_evaluation_orchestrator() -> TripEvaluationOrchestrator:
    """Build an orchestrator with no routes for isolated API tests."""

    return TripEvaluationOrchestrator(
        route_provider=InMemoryRouteProvider(()),
        energy_cost_estimator=InMemoryEnergyCostEstimator({}),
    )


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
            json=_valid_trip_payload(),
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
                "cost_breakdown": {
                    "monetary_cost": "3.75",
                    "time_cost": "4.5000",
                    "generalized_cost": "8.2500",
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
    app.dependency_overrides[get_trip_evaluation_orchestrator] = (
        _build_empty_trip_evaluation_orchestrator
    )

    try:
        client = TestClient(app)

        response = client.post(
            "/trip-evaluations",
            json=_valid_trip_payload(),
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
    finally:
        app.dependency_overrides.clear()


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
            json=_valid_trip_payload(),
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
        assert evaluation["cost_breakdown"] is None

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
            json=_valid_trip_payload(),
        )

        assert response.status_code == 200

        body = response.json()
        evaluation = body["route_evaluations"][0]

        assert evaluation["energy_estimate"] is None
        assert evaluation["cost_breakdown"] is None
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
            "destination": _location_payload(
                "Destination",
                source_id="destination-place-id",
            ),
            "value_of_time_per_hour": "18.00",
            "gasoline": {
                "fuel_efficiency_mpg": "30",
                "fuel_grade": "regular",
                "fuel_price_per_gallon": "4.50",
            },
        },
        {
            "origin": {
                "display_name": "   ",
                "latitude": 32.88,
                "longitude": -117.23,
            },
            "destination": _location_payload(
                "Destination",
                source_id="destination-place-id",
            ),
            "value_of_time_per_hour": "18.00",
            "gasoline": {
                "fuel_efficiency_mpg": "30",
                "fuel_grade": "regular",
                "fuel_price_per_gallon": "4.50",
            },
        },
        {
            "origin": _location_payload(
                "Origin",
                source_id="origin-place-id",
            ),
            "destination": {
                "display_name": "   ",
                "latitude": 32.88,
                "longitude": -117.23,
            },
            "value_of_time_per_hour": "18.00",
            "gasoline": {
                "fuel_efficiency_mpg": "30",
                "fuel_grade": "regular",
                "fuel_price_per_gallon": "4.50",
            },
        },
        {
            "origin": "Origin",
            "destination": _location_payload(
                "Destination",
                source_id="destination-place-id",
            ),
            "value_of_time_per_hour": "18.00",
            "gasoline": {
                "fuel_efficiency_mpg": "30",
                "fuel_grade": "regular",
                "fuel_price_per_gallon": "4.50",
            },
        },
        {
            **_valid_trip_payload(),
            "value_of_time_per_hour": "-0.01",
        },
        {
            "origin": _location_payload(
                "Origin",
                source_id="origin-place-id",
            ),
            "destination": _location_payload(
                "Destination",
                source_id="destination-place-id",
            ),
            "value_of_time_per_hour": "18.00",
        },
        {
            **_valid_trip_payload(),
            "gasoline": {
                "fuel_efficiency_mpg": "0",
                "fuel_grade": "regular",
                "fuel_price_per_gallon": "4.50",
            },
        },
        {
            **_valid_trip_payload(),
            "gasoline": {
                "fuel_efficiency_mpg": "30",
                "fuel_grade": "diesel",
                "fuel_price_per_gallon": "4.50",
            },
        },
        {
            **_valid_trip_payload(),
            "gasoline": {
                "fuel_efficiency_mpg": "30",
                "fuel_grade": "regular",
                "fuel_price_per_gallon": "-0.01",
            },
        },
    ],
)
def test_trip_evaluation_endpoint_rejects_invalid_request(
    payload: dict[str, object],
) -> None:
    app.dependency_overrides[get_trip_evaluation_orchestrator] = (
        _build_empty_trip_evaluation_orchestrator
    )

    try:
        client = TestClient(app)

        response = client.post(
            "/trip-evaluations",
            json=payload,
        )

        assert response.status_code == 422
        assert response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_trip_evaluation_endpoint_changes_recommendation_with_value_of_time() -> None:
    faster_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal("5.00"),
    )
    cheaper_route = RouteCandidate(
        distance_meters=12_000,
        duration_seconds=1_800,
        toll_cost=Decimal(0),
    )

    def override_trip_evaluation_orchestrator() -> TripEvaluationOrchestrator:
        return TripEvaluationOrchestrator(
            route_provider=InMemoryRouteProvider(
                (
                    faster_route,
                    cheaper_route,
                )
            ),
            energy_cost_estimator=InMemoryEnergyCostEstimator(
                {
                    faster_route: EnergyEstimate(
                        cost=Decimal("3.00"),
                    ),
                    cheaper_route: EnergyEstimate(
                        cost=Decimal("2.00"),
                    ),
                }
            ),
        )

    app.dependency_overrides[get_trip_evaluation_orchestrator] = (
        override_trip_evaluation_orchestrator
    )

    try:
        client = TestClient(app)

        base_payload = {
            "origin": _location_payload(
                "Origin",
                source_id="origin-place-id",
            ),
            "destination": _location_payload(
                "Destination",
                source_id="destination-place-id",
            ),
            "gasoline": {
                "fuel_efficiency_mpg": "30",
                "fuel_grade": "regular",
                "fuel_price_per_gallon": "4.50",
            },
        }

        low_value_response = client.post(
            "/trip-evaluations",
            json={
                **base_payload,
                "value_of_time_per_hour": "10.00",
            },
        )

        high_value_response = client.post(
            "/trip-evaluations",
            json={
                **base_payload,
                "value_of_time_per_hour": "30.00",
            },
        )

        assert low_value_response.status_code == 200
        assert high_value_response.status_code == 200

        low_value_body = low_value_response.json()
        high_value_body = high_value_response.json()

        assert low_value_body["decision"]["recommended_route"] == {
            "distance_meters": 12_000,
            "duration_seconds": 1_800,
            "toll_cost": "0",
        }
        assert low_value_body["decision"]["reason"] == "cheaper_route_worth_extra_time"

        assert high_value_body["decision"]["recommended_route"] == {
            "distance_meters": 10_000,
            "duration_seconds": 900,
            "toll_cost": "5.00",
        }
        assert high_value_body["decision"]["reason"] == "faster_route_worth_extra_cost"

        low_value_faster_cost = Decimal(
            low_value_body["route_evaluations"][0]["cost_breakdown"]["generalized_cost"]
        )
        low_value_cheaper_cost = Decimal(
            low_value_body["route_evaluations"][1]["cost_breakdown"]["generalized_cost"]
        )

        high_value_faster_cost = Decimal(
            high_value_body["route_evaluations"][0]["cost_breakdown"]["generalized_cost"]
        )
        high_value_cheaper_cost = Decimal(
            high_value_body["route_evaluations"][1]["cost_breakdown"]["generalized_cost"]
        )

        assert low_value_faster_cost == Decimal("10.50")
        assert low_value_cheaper_cost == Decimal("7.00")

        assert high_value_faster_cost == Decimal("15.50")
        assert high_value_cheaper_cost == Decimal("17.00")
    finally:
        app.dependency_overrides.clear()
