"""Security and failure hardening for V2 trip evaluations."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from routevalue.api.authentication import get_authentication_verifier
from routevalue.api.dependencies import (
    get_google_routes_api_key,
    get_google_routes_http_client,
)
from routevalue.api.preferences import get_user_preferences_repository
from routevalue.api.saved_vehicles import (
    get_saved_vehicle_repository,
    get_vehicle_specification_provider,
)
from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import (
    get_profile_driven_trip_evaluation_service,
)
from routevalue.application.gasoline_evaluation import GasolineEvaluationContext
from routevalue.application.identity import (
    AuthenticatedUser,
    AuthenticationVerificationUnavailableError,
    InvalidAuthenticationError,
    VerifiedExternalIdentity,
)
from routevalue.application.models import (
    ProvidedRoute,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
)
from routevalue.application.ports import EnergyCostEstimator
from routevalue.application.preferences import UserPreferences
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
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.infrastructure.energy.gasoline import GasolineEnergyCostEstimator
from routevalue.infrastructure.persistence.saved_vehicles import (
    SavedVehiclePersistenceError,
)
from routevalue.infrastructure.routing.google_routes import (
    GoogleRoutesError,
    GoogleRoutesHTTPError,
    GoogleRoutesResponseError,
    GoogleRoutesTransportError,
)
from routevalue.main import create_app

_PATH = "/api/v2/trip-evaluations"
_SECRET = "sensitive-private-infrastructure-detail"


def _body() -> dict[str, object]:
    return {
        "origin": {
            "display_name": "UC San Diego",
            "latitude": 32.8801,
            "longitude": -117.2340,
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


def _saved_vehicle(vehicle_id: SavedVehicleId) -> SavedVehicle:
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
        specification=GasolineVehicleSpecification(
            combined_mpg=Decimal(25),
            fuel_grade=GasolineGrade.REGULAR,
        ),
        specification_retrieved_at=datetime(2026, 10, 1, tzinfo=UTC),
        saved_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


class FakePreferencesRepository:
    def __init__(self, preferences: UserPreferences) -> None:
        self.preferences = preferences
        self.reads: list[UserId] = []

    def get_preferences(self, user_id: UserId) -> UserPreferences:
        self.reads.append(user_id)
        return self.preferences

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        raise AssertionError("evaluation cannot update preferences")


class FakeVehicleRepository:
    def __init__(
        self,
        vehicles: dict[tuple[UserId, SavedVehicleId], SavedVehicle],
        *,
        failure: Exception | None = None,
    ) -> None:
        self.vehicles = vehicles
        self.failure = failure
        self.calls: list[tuple[UserId, SavedVehicleId]] = []

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        self.calls.append((user_id, vehicle_id))

        if self.failure is not None:
            raise self.failure

        return self.vehicles.get((user_id, vehicle_id))

    def list_vehicles(self, user_id: UserId) -> Sequence[SavedVehicle]:
        raise AssertionError("evaluation cannot list the vehicle catalog")

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        raise AssertionError("evaluation cannot create vehicles")

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        raise AssertionError("evaluation cannot delete vehicles")


class FakeRoutes:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls = 0

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        self.calls += 1

        if self.failure is not None:
            raise self.failure

        return (
            ProvidedRoute(
                route=RouteCandidate(
                    distance_meters=10_000,
                    duration_seconds=900,
                    toll_cost=Decimal(0),
                )
            ),
        )


def _estimator(
    context: GasolineEvaluationContext,
) -> EnergyCostEstimator:
    return GasolineEnergyCostEstimator(
        vehicle=context.vehicle,
        fuel_price_quote=context.fuel_price_quote,
    )


def _client(
    user_id: UserId,
    preferences: UserPreferences,
    vehicles: dict[tuple[UserId, SavedVehicleId], SavedVehicle],
    *,
    vehicle_failure: Exception | None = None,
    route_failure: Exception | None = None,
) -> tuple[TestClient, FakeRoutes, FakeVehicleRepository]:
    """Exercise the real application service behind the HTTP boundary."""

    vehicle_repository = FakeVehicleRepository(
        vehicles,
        failure=vehicle_failure,
    )

    profile_service = ProfileResolutionService(
        preferences_repository=FakePreferencesRepository(preferences),
        saved_vehicle_repository=vehicle_repository,
    )

    routes = FakeRoutes(route_failure)

    evaluation_service = ProfileDrivenTripEvaluationService(
        profile_resolution_service=profile_service,
        route_provider=routes,
        gasoline_estimator_factory=_estimator,
    )

    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: (
        evaluation_service
    )

    return TestClient(app), routes, vehicle_repository


def _unreachable_service() -> ProfileDrivenTripEvaluationService:
    raise AssertionError("authentication must prevent evaluation setup")


class RejectingVerifier:
    def verify_token(self, token: str) -> VerifiedExternalIdentity:
        raise InvalidAuthenticationError(f"{_SECRET}: {token}")


class UnavailableVerifier:
    def verify_token(self, token: str) -> VerifiedExternalIdentity:
        raise AuthenticationVerificationUnavailableError(_SECRET)


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Basic invalid",
        "Bearer",
    ],
)
def test_missing_or_malformed_authentication_cannot_evaluate(
    authorization: str | None,
) -> None:
    app = create_app()

    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = _unreachable_service

    headers = {"Authorization": authorization} if authorization is not None else {}

    with TestClient(app) as client:
        response = client.post(_PATH, json=_body(), headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_bearer_token_is_rejected_without_leaks() -> None:
    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: RejectingVerifier()
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = _unreachable_service

    with TestClient(app) as client:
        response = client.post(
            _PATH,
            json=_body(),
            headers={"Authorization": "Bearer private-test-token"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert "private-test-token" not in response.text
    assert _SECRET not in response.text


def test_authentication_service_failure_is_sanitized() -> None:
    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: UnavailableVerifier()
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = _unreachable_service

    with TestClient(app) as client:
        response = client.post(
            _PATH,
            json=_body(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "authentication_service_unavailable"
    assert _SECRET not in response.text


def test_foreign_and_missing_vehicle_are_indistinguishable() -> None:
    owner = UserId(value=uuid4())
    caller = UserId(value=uuid4())

    foreign_id = SavedVehicleId(value=uuid4())
    nonexistent_id = SavedVehicleId(value=uuid4())

    client, routes, repository = _client(
        caller,
        UserPreferences(value_of_time_per_hour=Decimal(25)),
        {(owner, foreign_id): _saved_vehicle(foreign_id)},
    )

    responses: list[tuple[int, object]] = []

    for vehicle_id in (foreign_id, nonexistent_id):
        body = _body()
        body["saved_vehicle_id"] = str(vehicle_id.value)

        response = client.post(_PATH, json=body)
        responses.append((response.status_code, response.json()))

    assert responses == [
        (
            404,
            {
                "code": "saved_vehicle_not_found",
                "detail": "Saved vehicle was not found.",
            },
        ),
        (
            404,
            {
                "code": "saved_vehicle_not_found",
                "detail": "Saved vehicle was not found.",
            },
        ),
    ]

    assert repository.calls == [
        (caller, foreign_id),
        (caller, nonexistent_id),
    ]
    assert routes.calls == 0


def test_stale_default_does_not_trigger_routing() -> None:
    user_id = UserId(value=uuid4())
    deleted_id = SavedVehicleId(value=uuid4())

    client, routes, _ = _client(
        user_id,
        UserPreferences(
            value_of_time_per_hour=Decimal(25),
            default_vehicle_id=deleted_id,
        ),
        {},
    )

    response = client.post(_PATH, json=_body())

    assert response.status_code == 409
    assert response.json()["code"] == "default_vehicle_unavailable"
    assert routes.calls == 0


def test_missing_value_of_time_does_not_trigger_routing() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    client, routes, repository = _client(
        user_id,
        UserPreferences(default_vehicle_id=vehicle_id),
        {(user_id, vehicle_id): _saved_vehicle(vehicle_id)},
    )

    response = client.post(_PATH, json=_body())

    assert response.status_code == 409
    assert response.json()["code"] == "value_of_time_not_configured"
    assert repository.calls == []
    assert routes.calls == 0


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (
            SavedVehiclePersistenceError(_SECRET),
            500,
            "profile_state_invalid",
        ),
        (
            SQLAlchemyError(_SECRET),
            503,
            "profile_service_unavailable",
        ),
    ],
)
def test_vehicle_storage_errors_are_safe(
    failure: Exception,
    status: int,
    code: str,
) -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    client, routes, _ = _client(
        user_id,
        UserPreferences(
            value_of_time_per_hour=Decimal(25),
            default_vehicle_id=vehicle_id,
        ),
        {},
        vehicle_failure=failure,
    )

    response = client.post(_PATH, json=_body())

    assert response.status_code == status
    assert response.json()["code"] == code
    assert _SECRET not in response.text
    assert routes.calls == 0


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (
            GoogleRoutesTransportError(_SECRET),
            503,
            "routing_service_unavailable",
        ),
        (
            GoogleRoutesHTTPError(429),
            503,
            "routing_service_unavailable",
        ),
        (
            GoogleRoutesHTTPError(403),
            502,
            "routing_service_error",
        ),
        (
            GoogleRoutesResponseError(_SECRET),
            502,
            "routing_response_invalid",
        ),
        (
            GoogleRoutesError(_SECRET),
            502,
            "routing_service_error",
        ),
    ],
)
def test_routing_failures_use_existing_safe_error_mapping(
    failure: Exception,
    status: int,
    code: str,
) -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    client, routes, _ = _client(
        user_id,
        UserPreferences(
            value_of_time_per_hour=Decimal(25),
            default_vehicle_id=vehicle_id,
        ),
        {(user_id, vehicle_id): _saved_vehicle(vehicle_id)},
        route_failure=failure,
    )

    response = client.post(_PATH, json=_body())

    assert response.status_code == status
    assert response.json()["code"] == code
    assert _SECRET not in response.text
    assert routes.calls == 1


def test_missing_routing_configuration_is_safely_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_ROUTES_API_KEY", raising=False)

    user_id = UserId(value=uuid4())

    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_user_preferences_repository] = lambda: FakePreferencesRepository(
        UserPreferences()
    )
    app.dependency_overrides[get_saved_vehicle_repository] = lambda: FakeVehicleRepository({})

    with TestClient(app) as client:
        response = client.post(_PATH, json=_body())

    assert response.status_code == 500
    assert response.json()["code"] == "service_configuration_error"
    assert "GOOGLE_ROUTES_API_KEY" not in response.text


def test_evaluation_uses_snapshot_without_vehicle_catalog_lookup() -> None:
    """Exercise actual production dependency wiring with mocked Google HTTP."""

    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    preferences = FakePreferencesRepository(
        UserPreferences(
            value_of_time_per_hour=Decimal(25),
            default_vehicle_id=vehicle_id,
        )
    )
    vehicles = FakeVehicleRepository({(user_id, vehicle_id): _saved_vehicle(vehicle_id)})

    google_requests: list[httpx.Request] = []

    def mocked_google_response(request: httpx.Request) -> httpx.Response:
        google_requests.append(request)

        return httpx.Response(
            status_code=200,
            json={
                "routes": [
                    {
                        "distanceMeters": 16093,
                        "duration": "900s",
                    }
                ]
            },
        )

    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_user_preferences_repository] = lambda: preferences
    app.dependency_overrides[get_saved_vehicle_repository] = lambda: vehicles
    app.dependency_overrides[get_google_routes_api_key] = lambda: "local-test-key"

    def forbidden_catalog_provider() -> object:
        raise AssertionError("FuelEconomy.gov must not be called")

    app.dependency_overrides[get_vehicle_specification_provider] = forbidden_catalog_provider

    with httpx.Client(transport=httpx.MockTransport(mocked_google_response)) as google_client:
        app.dependency_overrides[get_google_routes_http_client] = lambda: google_client

        with TestClient(app) as client:
            response = client.post(_PATH, json=_body())

    assert response.status_code == 200
    assert response.json()["decision"]["eligible_count"] == 1

    # Existing Google Routes adapter makes baseline and avoid-tolls calls.
    assert len(google_requests) == 2
    assert all(request.headers["X-Goog-Api-Key"] == "local-test-key" for request in google_requests)

    assert preferences.reads == [user_id]
    assert vehicles.calls == [(user_id, vehicle_id)]
