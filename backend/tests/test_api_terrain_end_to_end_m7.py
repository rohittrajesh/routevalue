"""M7-H4-C HTTP tests for disabled-by-default terrain integration."""

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
from routevalue.application.models import VehicleCatalogConfiguration
from routevalue.application.ports import (
    RouteProvider,
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.preferences import UserPreferences
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.domain.energy_consumption import (
    estimate_baseline_electric_consumption,
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
    VehicleEnergySpecification,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource
from routevalue.main import create_app

_PATH = "/api/v2/trip-evaluations"


def _route(*, toll: Decimal | None = Decimal(2)) -> RouteCandidate:
    return RouteCandidate(
        distance_meters=160_934,
        duration_seconds=3600,
        toll_cost=toll,
    )


def _mass() -> VehicleMass:
    return VehicleMass(
        kilograms=Decimal(1800),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
    )


def _gasoline(*, known_mass: bool = True) -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=_mass() if known_mass else None,
    )


def _electric(*, known_mass: bool = True) -> ElectricVehicleSpecification:
    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=_mass() if known_mass else None,
    )


def _vehicle(
    vehicle_id: SavedVehicleId,
    specification: VehicleEnergySpecification,
) -> SavedVehicle:
    now = datetime(2026, 10, 13, tzinfo=UTC)

    return SavedVehicle(
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


def _body(
    *,
    gasoline_price: str | None = None,
    electricity_price: str | None = None,
) -> dict[str, object]:
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

    if gasoline_price is not None:
        body["gasoline"] = {
            "fuel_price_per_gallon": gasoline_price,
        }

    if electricity_price is not None:
        body["electricity"] = {
            "price_per_kilowatt_hour": electricity_price,
        }

    return body


def _client(
    specification: VehicleEnergySpecification,
    *,
    user_has_vehicle: bool = True,
    configured_value_of_time: bool = True,
    toll: Decimal | None = Decimal(2),
) -> tuple[TestClient, Mock]:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    preferences = Mock(spec=UserPreferencesRepository)
    preferences.get_preferences.return_value = UserPreferences(
        value_of_time_per_hour=(Decimal(25) if configured_value_of_time else None),
        default_vehicle_id=vehicle_id,
    )

    vehicles = Mock(spec=SavedVehicleRepository)
    vehicles.get_vehicle.return_value = (
        _vehicle(vehicle_id, specification) if user_has_vehicle else None
    )

    routing = Mock(spec=RouteProvider)
    from routevalue.application.models import ProvidedRoute

    routing.get_routes.return_value = (ProvidedRoute(route=_route(toll=toll)),)

    service = build_terrain_v2_evaluation_service(
        preferences_repository=cast(UserPreferencesRepository, preferences),
        saved_vehicle_repository=cast(SavedVehicleRepository, vehicles),
        route_provider=cast(RouteProvider, routing),
    )

    app = create_app()
    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: service

    return TestClient(app), routing


def test_gasoline_http_preserves_exact_m5_consumption() -> None:
    client, routing = _client(_gasoline())

    with client:
        response = client.post(
            _PATH,
            json=_body(gasoline_price="4.50"),
        )

    assert response.status_code == 200

    result = response.json()
    energy = result["route_evaluations"][0]["energy_estimate"]

    baseline = estimate_baseline_gasoline_consumption(
        _route(),
        vehicle=_gasoline(),
    )

    assert energy["consumption"]["energy_type"] == "gasoline"
    assert Decimal(energy["consumption"]["gallons"]) == baseline.gallons
    assert Decimal(energy["cost"]) == baseline.gallons * Decimal("4.50")
    assert result["decision"]["eligible_count"] == 1
    assert routing.get_routes.call_count == 1


def test_electric_http_preserves_exact_m5_consumption() -> None:
    client, routing = _client(_electric())

    with client:
        response = client.post(
            _PATH,
            json=_body(electricity_price="0.30"),
        )

    assert response.status_code == 200

    result = response.json()
    energy = result["route_evaluations"][0]["energy_estimate"]

    baseline = estimate_baseline_electric_consumption(
        _route(),
        vehicle=_electric(),
    )

    assert energy["consumption"]["energy_type"] == "electricity"
    assert Decimal(energy["consumption"]["kilowatt_hours"]) == (baseline.kilowatt_hours)
    assert Decimal(energy["cost"]) == (baseline.kilowatt_hours * Decimal("0.30"))
    assert routing.get_routes.call_count == 1


@pytest.mark.parametrize("powertrain", ["gasoline", "electric"])
def test_missing_vehicle_mass_does_not_break_http(
    powertrain: str,
) -> None:
    if powertrain == "gasoline":
        specification: VehicleEnergySpecification = _gasoline(known_mass=False)
        body = _body(gasoline_price="4.50")
    else:
        specification = _electric(known_mass=False)
        body = _body(electricity_price="0.30")

    client, _ = _client(specification)

    with client:
        response = client.post(_PATH, json=body)

    assert response.status_code == 200
    assert response.json()["decision"]["eligible_count"] == 1


def test_unavailable_vehicle_does_not_trigger_routing() -> None:
    client, routing = _client(
        _gasoline(),
        user_has_vehicle=False,
    )

    with client:
        response = client.post(
            _PATH,
            json=_body(gasoline_price="4.50"),
        )

    assert response.status_code == 409
    assert response.json()["code"] == "default_vehicle_unavailable"
    routing.get_routes.assert_not_called()


def test_missing_value_of_time_does_not_trigger_routing() -> None:
    client, routing = _client(
        _gasoline(),
        configured_value_of_time=False,
    )

    with client:
        response = client.post(
            _PATH,
            json=_body(gasoline_price="4.50"),
        )

    assert response.status_code == 409
    assert response.json()["code"] == "value_of_time_not_configured"
    routing.get_routes.assert_not_called()


@pytest.mark.parametrize(
    ("specification", "body"),
    [
        (_gasoline(), _body(electricity_price="0.30")),
        (_electric(), _body(gasoline_price="4.50")),
    ],
)
def test_price_powertrain_mismatch_rejected_before_routing(
    specification: VehicleEnergySpecification,
    body: dict[str, object],
) -> None:
    client, routing = _client(specification)

    with client:
        response = client.post(_PATH, json=body)

    assert response.status_code == 409
    assert response.json()["code"] == "energy_input_mismatch"
    routing.get_routes.assert_not_called()


def test_missing_toll_preserves_ineligibility() -> None:
    client, _ = _client(_gasoline(), toll=None)

    with client:
        response = client.post(
            _PATH,
            json=_body(gasoline_price="4.50"),
        )

    assert response.status_code == 200

    result = response.json()
    evaluation = result["route_evaluations"][0]

    assert not evaluation["eligibility"]["eligible"]
    assert evaluation["eligibility"]["reason"] == "missing_toll_cost"
    assert evaluation["cost_breakdown"] is None
    assert result["decision"]["eligible_count"] == 0
    assert result["decision"]["missing_data_present"] is True


@pytest.mark.parametrize("powertrain", ["gasoline", "electric"])
def test_zero_price_remains_known_and_eligible(
    powertrain: str,
) -> None:
    if powertrain == "gasoline":
        specification: VehicleEnergySpecification = _gasoline()
        body = _body(gasoline_price="0")
    else:
        specification = _electric()
        body = _body(electricity_price="0")

    client, _ = _client(specification)

    with client:
        response = client.post(_PATH, json=body)

    assert response.status_code == 200

    result = response.json()
    energy = result["route_evaluations"][0]["energy_estimate"]

    assert Decimal(energy["cost"]) == 0
    assert result["decision"]["eligible_count"] == 1
    assert not result["decision"]["missing_data_present"]


def test_http_results_are_deterministic() -> None:
    client, routing = _client(_gasoline())
    body = _body(gasoline_price="4.50")

    with client:
        first = client.post(_PATH, json=body)
        second = client.post(_PATH, json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert routing.get_routes.call_count == 2
