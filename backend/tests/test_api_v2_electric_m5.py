"""M5 authenticated V2 HTTP tests for gasoline and BEV evaluations."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import (
    get_profile_driven_trip_evaluation_service,
)
from routevalue.application.electric_evaluation import (
    ElectricEvaluationContext,
)
from routevalue.application.gasoline_evaluation import (
    GasolineEvaluationContext,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.models import (
    ProvidedRoute,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
)
from routevalue.application.ports import EnergyCostEstimator
from routevalue.application.preferences import UserPreferences
from routevalue.application.profile_resolution import (
    ProfileResolutionService,
)
from routevalue.application.profile_trip_evaluation import (
    ProfileDrivenTripEvaluationService,
)
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleSnapshot,
)
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
    VehicleEnergySpecification,
)
from routevalue.infrastructure.energy.electric import (
    ElectricEnergyCostEstimator,
)
from routevalue.infrastructure.energy.gasoline import (
    GasolineEnergyCostEstimator,
)
from routevalue.main import create_app


class PreferencesRepository:
    def __init__(self, preferences: UserPreferences) -> None:
        self.preferences = preferences

    def get_preferences(self, user_id: UserId) -> UserPreferences:
        return self.preferences

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        raise AssertionError("evaluation cannot modify preferences")


class VehicleRepository:
    def __init__(
        self,
        user_id: UserId,
        vehicle: SavedVehicle,
    ) -> None:
        self.user_id = user_id
        self.vehicle = vehicle

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        if user_id == self.user_id and vehicle_id == self.vehicle.id:
            return self.vehicle

        return None

    def list_vehicles(
        self,
        user_id: UserId,
    ) -> Sequence[SavedVehicle]:
        raise AssertionError("evaluation cannot list vehicles")

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        raise AssertionError("evaluation cannot save vehicles")

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        raise AssertionError("evaluation cannot delete vehicles")


class RecordingRoutes:
    def __init__(self) -> None:
        self.calls = 0

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        self.calls += 1

        return (
            ProvidedRoute(
                route=RouteCandidate(
                    distance_meters=201_168,
                    duration_seconds=3600,
                    toll_cost=Decimal("4.00"),
                )
            ),
        )


def _gasoline_factory(
    context: GasolineEvaluationContext,
) -> EnergyCostEstimator:
    return GasolineEnergyCostEstimator(
        vehicle=context.vehicle,
        fuel_price_quote=context.fuel_price_quote,
    )


def _electric_factory(
    context: ElectricEvaluationContext,
) -> EnergyCostEstimator:
    return ElectricEnergyCostEstimator(
        vehicle=context.vehicle,
        electricity_price_quote=context.electricity_price_quote,
    )


def _app(
    specification: VehicleEnergySpecification,
) -> tuple[FastAPI, RecordingRoutes]:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    vehicle = SavedVehicle(
        id=vehicle_id,
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Test",
            model="Vehicle",
            configuration="Baseline",
            source="fueleconomy_gov",
            source_id="12345",
        ),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 1, tzinfo=UTC),
        saved_at=datetime(2026, 10, 2, tzinfo=UTC),
    )

    preferences = PreferencesRepository(
        UserPreferences(
            value_of_time_per_hour=Decimal(20),
            default_vehicle_id=vehicle_id,
        )
    )
    vehicles = VehicleRepository(user_id, vehicle)
    routes = RecordingRoutes()

    service = ProfileDrivenTripEvaluationService(
        profile_resolution_service=ProfileResolutionService(
            preferences_repository=preferences,
            saved_vehicle_repository=vehicles,
        ),
        route_provider=routes,
        gasoline_estimator_factory=_gasoline_factory,
        electric_estimator_factory=_electric_factory,
    )

    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: service

    return app, routes


def _bev() -> ElectricVehicleSpecification:
    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.285"),
    )


def _gasoline() -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )


def _body(
    *,
    electricity: str | None = None,
    gasoline: str | None = None,
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

    if electricity is not None:
        body["electricity"] = {
            "price_per_kilowatt_hour": electricity,
        }

    if gasoline is not None:
        body["gasoline"] = {
            "fuel_price_per_gallon": gasoline,
        }

    return body


def test_bev_http_response_includes_kwh_and_cost() -> None:
    app, routes = _app(_bev())

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/trip-evaluations",
            json=_body(electricity="0.31"),
        )

    assert response.status_code == 200

    body = response.json()
    energy = body["route_evaluations"][0]["energy_estimate"]

    assert energy["consumption"]["energy_type"] == "electricity"
    assert Decimal(energy["consumption"]["kilowatt_hours"]) == Decimal("35.625")
    assert Decimal(energy["cost"]) == Decimal("11.04375")

    assert body["decision"]["reason"] == "only_eligible_route"
    assert routes.calls == 1


def test_gasoline_http_response_includes_gallons_and_cost() -> None:
    app, routes = _app(_gasoline())

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/trip-evaluations",
            json=_body(gasoline="4.50"),
        )

    assert response.status_code == 200

    energy = response.json()["route_evaluations"][0]["energy_estimate"]

    assert energy["consumption"]["energy_type"] == "gasoline"
    assert Decimal(energy["consumption"]["gallons"]) == Decimal(5)
    assert Decimal(energy["cost"]) == Decimal("22.50")

    assert routes.calls == 1


def test_zero_electricity_price_returns_known_zero_cost() -> None:
    app, routes = _app(_bev())

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/trip-evaluations",
            json=_body(electricity="0"),
        )

    assert response.status_code == 200

    energy = response.json()["route_evaluations"][0]["energy_estimate"]

    assert Decimal(energy["cost"]) == Decimal(0)
    assert Decimal(energy["consumption"]["kilowatt_hours"]) > 0

    assert routes.calls == 1


@pytest.mark.parametrize(
    ("specification", "body"),
    [
        (_bev(), _body(gasoline="4.50")),
        (_gasoline(), _body(electricity="0.31")),
    ],
)
def test_price_powertrain_mismatch_returns_409_before_routing(
    specification: VehicleEnergySpecification,
    body: dict[str, object],
) -> None:
    app, routes = _app(specification)

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/trip-evaluations",
            json=body,
        )

    assert response.status_code == 409
    assert response.json()["code"] == "energy_input_mismatch"
    assert routes.calls == 0


@pytest.mark.parametrize(
    "body,expected_status",
    [
        (_body(), 409),
        (_body(electricity="0.31", gasoline="4.50"), 422),
    ],
)
def test_missing_saved_rate_and_duplicate_prices_are_rejected(
    body: dict[str, object],
    expected_status: int,
) -> None:
    app, routes = _app(_bev())

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/trip-evaluations",
            json=body,
        )

    assert response.status_code == expected_status
    if expected_status == 409:
        assert response.json()["code"] == "electricity_price_not_configured"
    assert routes.calls == 0


@pytest.mark.parametrize(
    "invalid_price",
    ["-0.01", "NaN", "Infinity", "-Infinity"],
)
def test_invalid_electricity_price_returns_422(
    invalid_price: str,
) -> None:
    app, routes = _app(_bev())

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/trip-evaluations",
            json=_body(electricity=invalid_price),
        )

    assert response.status_code == 422
    assert routes.calls == 0


def test_client_cannot_override_saved_bev_efficiency() -> None:
    app, routes = _app(_bev())

    body = _body(electricity="0.31")
    body["electricity"] = {
        "price_per_kilowatt_hour": "0.31",
        "combined_kwh_per_mile": "0.001",
    }

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/trip-evaluations",
            json=body,
        )

    assert response.status_code == 422
    assert routes.calls == 0
