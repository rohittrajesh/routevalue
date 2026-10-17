"""M9-E2-B authenticated HTTP terrain-status regression tests."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from routevalue.api.terrain_v2_composition import (
    build_terrain_v2_evaluation_service,
)
from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import (
    get_profile_driven_trip_evaluation_service,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.models import (
    ProvidedRoute,
    VehicleCatalogConfiguration,
)
from routevalue.application.ports import (
    RouteProvider,
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.preferences import UserPreferences
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
    VehicleEnergySpecification,
)
from routevalue.domain.vehicle_mass import (
    VehicleMass,
    VehicleMassSource,
)
from routevalue.main import create_app


def _client(
    *,
    electric: bool = False,
    known_mass: bool = True,
    route_count: int = 1,
) -> tuple[TestClient, Mock]:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    mass = (
        VehicleMass(
            kilograms=Decimal(1800),
            source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        )
        if known_mass
        else None
    )

    specification: VehicleEnergySpecification

    if electric:
        specification = ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.30"),
            vehicle_mass=mass,
        )
    else:
        specification = GasolineVehicleSpecification(
            combined_mpg=Decimal(30),
            fuel_grade=GasolineGrade.REGULAR,
            vehicle_mass=mass,
        )

    now = datetime(2026, 10, 16, tzinfo=UTC)

    saved_vehicle = SavedVehicle(
        id=vehicle_id,
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Example",
            model="Test",
            configuration="Standard",
            source="test",
            source_id="test-vehicle",
        ),
        specification=specification,
        specification_retrieved_at=now,
        saved_at=now,
    )

    preferences = Mock(spec=UserPreferencesRepository)

    preferences.get_preferences.return_value = UserPreferences(
        value_of_time_per_hour=Decimal(25),
        default_vehicle_id=vehicle_id,
    )

    vehicles = Mock(spec=SavedVehicleRepository)
    vehicles.get_vehicle.return_value = saved_vehicle

    routing = Mock(spec=RouteProvider)

    routing.get_routes.return_value = tuple(
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=160_934,
                duration_seconds=3600 + index * 60,
                toll_cost=Decimal(2),
            )
        )
        for index in range(route_count)
    )

    service = build_terrain_v2_evaluation_service(
        preferences_repository=cast(
            UserPreferencesRepository,
            preferences,
        ),
        saved_vehicle_repository=cast(
            SavedVehicleRepository,
            vehicles,
        ),
        route_provider=cast(RouteProvider, routing),
    )

    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)

    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: service

    return TestClient(app), routing


def _body(*, electric: bool = False) -> dict[str, object]:
    body: dict[str, object] = {
        "origin": {
            "display_name": "Origin",
            "latitude": 32.88,
            "longitude": -117.23,
        },
        "destination": {
            "display_name": "Destination",
            "latitude": 32.72,
            "longitude": -117.16,
        },
    }

    if electric:
        body["electricity"] = {
            "price_per_kilowatt_hour": "0.30",
        }
    else:
        body["gasoline"] = {
            "fuel_price_per_gallon": "4.50",
        }

    return body


@pytest.mark.parametrize("electric", [False, True])
def test_http_reports_disabled_terrain_and_retains_energy(
    electric: bool,
) -> None:
    client, routing = _client(electric=electric)

    with client:
        response = client.post(
            "/api/v2/trip-evaluations",
            json=_body(electric=electric),
        )

    assert response.status_code == 200

    data = response.json()
    status = data["terrain_status"]

    assert status["terrain_applied"] is False

    assert status["fallback_reasons"] == ["acquisition_disabled"]

    assert status["route_acquisition_statuses"] == ["unavailable"]

    assert status["route_coverage_fractions"] == [None]

    energy = data["route_evaluations"][0]["energy_estimate"]
    expected_type = "electricity" if electric else "gasoline"

    assert energy["consumption"]["energy_type"] == expected_type
    assert Decimal(energy["cost"]) > 0

    assert data["decision"]["eligible_count"] == 1

    routing.get_routes.assert_called_once()


def test_missing_vehicle_mass_is_reported_without_changing_eligibility() -> None:
    client, routing = _client(known_mass=False)

    with client:
        response = client.post(
            "/api/v2/trip-evaluations",
            json=_body(),
        )

    assert response.status_code == 200

    data = response.json()
    status = data["terrain_status"]

    assert status["terrain_applied"] is False

    assert "acquisition_disabled" in status["fallback_reasons"]

    assert "missing_vehicle_mass" in status["fallback_reasons"]

    assert data["decision"]["eligible_count"] == 1

    routing.get_routes.assert_called_once()


def test_route_diagnostics_preserve_candidate_order_and_count() -> None:
    client, routing = _client(route_count=2)

    with client:
        response = client.post(
            "/api/v2/trip-evaluations",
            json=_body(),
        )

    assert response.status_code == 200

    data = response.json()

    assert len(data["route_evaluations"]) == 2

    assert data["terrain_status"]["route_acquisition_statuses"] == [
        "unavailable",
        "unavailable",
    ]

    assert data["terrain_status"]["route_coverage_fractions"] == [
        None,
        None,
    ]

    assert data["decision"]["candidate_count"] == 2

    routing.get_routes.assert_called_once()


def test_openapi_documents_terrain_status() -> None:
    schema = create_app().openapi()["components"]["schemas"]

    assert "terrain_status" in schema["V2TripEvaluationResponse"]["properties"]

    assert "V2TerrainStatusResponse" in schema
