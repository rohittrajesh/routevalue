"""HTTP integration tests for authenticated V2 trip evaluation."""

from collections.abc import Sequence
from dataclasses import replace as replace_preferences
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import (
    get_profile_driven_trip_evaluation_service,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.models import (
    ProvidedRoute,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
)
from routevalue.application.preferences import UserPreferences, UserPreferencesPatch
from routevalue.application.profile_resolution import ProfileResolutionService
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
from routevalue.infrastructure.energy.gasoline import GasolineEnergyCostEstimator
from routevalue.infrastructure.persistence.user_preferences import (
    UserPreferencesPersistenceError,
)
from routevalue.main import create_app


class MemoryPreferences:
    """Provide stored preferences without allowing evaluation-time writes."""

    def __init__(
        self,
        preferences: dict[UserId, UserPreferences],
        error: Exception | None = None,
    ) -> None:
        self.preferences = preferences
        self.error = error

    def get_preferences(self, user_id: UserId) -> UserPreferences:
        if self.error is not None:
            raise self.error

        return self.preferences.get(user_id, UserPreferences())

    def update_preferences(self, user_id: UserId, changes: UserPreferencesPatch) -> UserPreferences:
        current = self.get_preferences(user_id)
        updated = replace_preferences(current, **changes)
        if updated == current:
            return current
        return self.save_preferences(user_id, updated)

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        raise AssertionError("evaluation must not save preferences")


class MemoryVehicles:
    """Implement owner-scoped saved vehicle lookups."""

    def __init__(
        self,
        vehicles: dict[tuple[UserId, SavedVehicleId], SavedVehicle],
    ) -> None:
        self.vehicles = vehicles

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        return self.vehicles.get((user_id, vehicle_id))

    def list_vehicles(self, user_id: UserId) -> Sequence[SavedVehicle]:
        raise AssertionError("evaluation must not list vehicles")

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        raise AssertionError("evaluation must not create vehicles")

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        raise AssertionError("evaluation must not delete vehicles")


class FakeRoutes:
    """Supply one normalized route without external routing requests."""

    def __init__(self) -> None:
        self.calls: list[RouteSearchRequest] = []

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        self.calls.append(request)

        return (
            ProvidedRoute(
                route=RouteCandidate(
                    distance_meters=1_609_344,
                    duration_seconds=3600,
                    toll_cost=Decimal("1.25"),
                )
            ),
        )


def _vehicle(
    vehicle_id: SavedVehicleId,
    *,
    specification: VehicleEnergySpecification | None = None,
) -> SavedVehicle:
    if specification is None:
        specification = GasolineVehicleSpecification(
            combined_mpg=Decimal(25),
            fuel_grade=GasolineGrade.REGULAR,
        )

    return SavedVehicle(
        id=vehicle_id,
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Toyota",
            model="Camry",
            configuration="2.5L 4cyl CVT (FWD)",
            source="fueleconomy_gov",
            source_id="12345",
        ),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 1, tzinfo=UTC),
        saved_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


def _body() -> dict[str, object]:
    return {
        "origin": {
            "display_name": "UC San Diego",
            "latitude": 32.8801,
            "longitude": -117.234,
        },
        "destination": {
            "display_name": "Downtown San Diego",
            "latitude": 32.7157,
            "longitude": -117.1611,
        },
        "gasoline": {
            "fuel_price_per_gallon": "4.50",
        },
    }


def _client(
    user_id: UserId,
    *,
    preferences: UserPreferences,
    vehicles: dict[tuple[UserId, SavedVehicleId], SavedVehicle],
    error: Exception | None = None,
) -> tuple[TestClient, FakeRoutes]:
    """Configure the real V2 application service behind the HTTP API."""

    routes = FakeRoutes()

    profile_service = ProfileResolutionService(
        preferences_repository=MemoryPreferences(
            {user_id: preferences},
            error=error,
        ),
        saved_vehicle_repository=MemoryVehicles(vehicles),
    )

    def build_estimator(
        context: object,
    ) -> GasolineEnergyCostEstimator:
        from routevalue.application.gasoline_evaluation import (
            GasolineEvaluationContext,
        )

        assert isinstance(context, GasolineEvaluationContext)

        return GasolineEnergyCostEstimator(
            vehicle=context.vehicle,
            fuel_price_quote=context.fuel_price_quote,
        )

    service = ProfileDrivenTripEvaluationService(
        profile_resolution_service=profile_service,
        route_provider=routes,
        gasoline_estimator_factory=build_estimator,
    )

    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)

    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: service

    return TestClient(app), routes


def test_default_vehicle_evaluation_uses_persisted_profile() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    client, routes = _client(
        user_id,
        preferences=UserPreferences(
            value_of_time_per_hour=Decimal(30),
            default_vehicle_id=vehicle_id,
        ),
        vehicles={(user_id, vehicle_id): _vehicle(vehicle_id)},
    )

    response = client.post("/api/v2/trip-evaluations", json=_body())

    assert response.status_code == 200

    body = response.json()

    assert body["decision"]["candidate_count"] == 1
    assert body["decision"]["eligible_count"] == 1
    assert body["decision"]["reason"] == "only_eligible_route"
    assert body["decision"]["missing_data_present"] is False

    evaluation = body["route_evaluations"][0]

    assert Decimal(evaluation["energy_estimate"]["cost"]) == Decimal(180)
    assert Decimal(evaluation["cost_breakdown"]["monetary_cost"]) == Decimal("181.25")
    assert Decimal(evaluation["cost_breakdown"]["time_cost"]) == Decimal(30)
    assert Decimal(evaluation["cost_breakdown"]["generalized_cost"]) == Decimal("211.25")

    assert len(routes.calls) == 1
    assert routes.calls[0].origin.display_name == "UC San Diego"


def test_explicit_owned_vehicle_overrides_default() -> None:
    user_id = UserId(value=uuid4())
    default_id = SavedVehicleId(value=uuid4())
    selected_id = SavedVehicleId(value=uuid4())

    selected_vehicle = _vehicle(
        selected_id,
        specification=GasolineVehicleSpecification(
            combined_mpg=Decimal(50),
            fuel_grade=GasolineGrade.PREMIUM,
        ),
    )

    client, routes = _client(
        user_id,
        preferences=UserPreferences(
            value_of_time_per_hour=Decimal(0),
            default_vehicle_id=default_id,
        ),
        vehicles={
            (user_id, default_id): _vehicle(default_id),
            (user_id, selected_id): selected_vehicle,
        },
    )

    body = _body()
    body["saved_vehicle_id"] = str(selected_id.value)
    body["gasoline"] = {"fuel_price_per_gallon": "5.00"}

    response = client.post("/api/v2/trip-evaluations", json=body)

    assert response.status_code == 200

    evaluation = response.json()["route_evaluations"][0]

    # 1000 miles / 50 stored MPG * $5.00 = $100 gasoline cost.
    assert Decimal(evaluation["energy_estimate"]["cost"]) == Decimal(100)
    assert len(routes.calls) == 1


def test_missing_value_of_time_returns_409_before_routing() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    client, routes = _client(
        user_id,
        preferences=UserPreferences(default_vehicle_id=vehicle_id),
        vehicles={(user_id, vehicle_id): _vehicle(vehicle_id)},
    )

    response = client.post("/api/v2/trip-evaluations", json=_body())

    assert response.status_code == 409
    assert response.json()["code"] == "value_of_time_not_configured"
    assert routes.calls == []


def test_missing_default_returns_409() -> None:
    user_id = UserId(value=uuid4())

    client, routes = _client(
        user_id,
        preferences=UserPreferences(
            value_of_time_per_hour=Decimal(25),
        ),
        vehicles={},
    )

    response = client.post("/api/v2/trip-evaluations", json=_body())

    assert response.status_code == 409
    assert response.json()["code"] == "default_vehicle_not_configured"
    assert routes.calls == []


def test_foreign_vehicle_is_hidden_with_404() -> None:
    user_id = UserId(value=uuid4())
    foreign_user = UserId(value=uuid4())
    foreign_id = SavedVehicleId(value=uuid4())

    client, routes = _client(
        user_id,
        preferences=UserPreferences(
            value_of_time_per_hour=Decimal(25),
        ),
        vehicles={
            (foreign_user, foreign_id): _vehicle(foreign_id),
        },
    )

    body = _body()
    body["saved_vehicle_id"] = str(foreign_id.value)

    response = client.post("/api/v2/trip-evaluations", json=body)

    assert response.status_code == 404
    assert response.json() == {
        "code": "saved_vehicle_not_found",
        "detail": "Saved vehicle was not found.",
    }
    assert routes.calls == []


def test_bev_returns_409_without_running_routes() -> None:
    """A BEV must reject gasoline pricing before acquiring routes."""

    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    bev = _vehicle(
        vehicle_id,
        specification=ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.285"),
        ),
    )

    client, routes = _client(
        user_id,
        preferences=UserPreferences(
            value_of_time_per_hour=Decimal(25),
            default_vehicle_id=vehicle_id,
        ),
        vehicles={(user_id, vehicle_id): bev},
    )

    response = client.post(
        "/api/v2/trip-evaluations",
        json=_body(),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "energy_input_mismatch"
    assert routes.calls == []


def test_database_error_returns_safe_503() -> None:
    user_id = UserId(value=uuid4())

    client, routes = _client(
        user_id,
        preferences=UserPreferences(),
        vehicles={},
        error=SQLAlchemyError("sensitive database connection detail"),
    )

    response = client.post("/api/v2/trip-evaluations", json=_body())

    assert response.status_code == 503
    assert response.json()["code"] == "profile_service_unavailable"
    assert "sensitive database" not in response.text
    assert routes.calls == []


def test_corrupted_persisted_profile_returns_safe_500() -> None:
    user_id = UserId(value=uuid4())

    client, routes = _client(
        user_id,
        preferences=UserPreferences(),
        vehicles={},
        error=UserPreferencesPersistenceError("sensitive persisted profile detail"),
    )

    response = client.post("/api/v2/trip-evaluations", json=_body())

    assert response.status_code == 500
    assert response.json()["code"] == "profile_state_invalid"
    assert "sensitive persisted" not in response.text
    assert routes.calls == []


def test_http_request_rejects_client_supplied_user_id() -> None:
    user_id = UserId(value=uuid4())

    client, routes = _client(
        user_id,
        preferences=UserPreferences(),
        vehicles={},
    )

    body = _body()
    body["user_id"] = str(uuid4())

    response = client.post("/api/v2/trip-evaluations", json=body)

    assert response.status_code == 422
    assert routes.calls == []
