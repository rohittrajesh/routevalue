"""Real PostgreSQL integration tests for authenticated V2 trip evaluation."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.engine import Engine

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
from routevalue.api.user_identity import get_user_identity_repository
from routevalue.application.identity import (
    InvalidAuthenticationError,
    VerifiedExternalIdentity,
)
from routevalue.application.models import VehicleCatalogConfiguration
from routevalue.application.preferences import UserPreferences
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleSnapshot,
)
from routevalue.domain.identity import UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    VehicleEnergySpecification,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    PostgresSavedVehicleRepository,
)
from routevalue.infrastructure.persistence.schema import users
from routevalue.infrastructure.persistence.user_identity import (
    PostgresUserIdentityRepository,
)
from routevalue.infrastructure.persistence.user_preferences import (
    PostgresUserPreferencesRepository,
)
from routevalue.main import create_app

_PATH = "/api/v2/trip-evaluations"


class TokenMappingVerifier:
    """Map fake bearer tokens to real persisted identity records."""

    def __init__(
        self,
        identities: dict[str, VerifiedExternalIdentity],
    ) -> None:
        self.identities = identities

    def verify_token(self, token: str) -> VerifiedExternalIdentity:
        identity = self.identities.get(token)

        if identity is None:
            raise InvalidAuthenticationError

        return identity


@dataclass(frozen=True, slots=True)
class PostgresEvaluationHarness:
    """Live PostgreSQL repositories behind an authenticated test API."""

    client: TestClient
    owner: UserId
    other: UserId
    preferences: PostgresUserPreferencesRepository
    vehicles: PostgresSavedVehicleRepository
    google_requests: list[httpx.Request]


def _identity(label: str) -> VerifiedExternalIdentity:
    return VerifiedExternalIdentity(
        issuer="https://routevalue-integration.example.test",
        subject=f"{label}-{uuid4().hex}",
    )


def _headers(token: str = "owner-token") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }


def _body(
    vehicle_id: UUID | None = None,
    *,
    price: str = "4.50",
) -> dict[str, object]:
    body: dict[str, object] = {
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
            "fuel_price_per_gallon": price,
        },
    }

    if vehicle_id is not None:
        body["saved_vehicle_id"] = str(vehicle_id)

    return body


def _snapshot(
    specification: VehicleEnergySpecification,
) -> SavedVehicleSnapshot:
    return SavedVehicleSnapshot(
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Toyota",
            model="Camry",
            configuration="2.5L 4cyl CVT (FWD)",
            source="fueleconomy_gov",
            source_id=uuid4().hex,
        ),
        specification=specification,
        specification_retrieved_at=datetime(
            2026,
            10,
            12,
            20,
            0,
            tzinfo=UTC,
        ),
    )


def _save_gasoline(
    harness: PostgresEvaluationHarness,
    user_id: UserId,
    *,
    mpg: str = "25",
    grade: GasolineGrade = GasolineGrade.REGULAR,
) -> SavedVehicle:
    return harness.vehicles.create_vehicle(
        user_id,
        _snapshot(
            GasolineVehicleSpecification(
                combined_mpg=Decimal(mpg),
                fuel_grade=grade,
            )
        ),
    )


def _configure(
    harness: PostgresEvaluationHarness,
    user_id: UserId,
    vehicle: SavedVehicle,
    *,
    value_of_time: str = "0",
) -> None:
    harness.preferences.save_preferences(
        user_id,
        UserPreferences(
            value_of_time_per_hour=Decimal(value_of_time),
            default_vehicle_id=vehicle.id,
        ),
    )


def _fake_google_response(
    request: httpx.Request,
    recorded_requests: list[httpx.Request],
) -> httpx.Response:
    """Return two routes with a meaningful time-versus-cost tradeoff."""

    recorded_requests.append(request)

    return httpx.Response(
        status_code=200,
        json={
            "routes": [
                {
                    "distanceMeters": 16093,
                    "duration": "1800s",
                    "polyline": {
                        "geoJsonLinestring": {
                            "type": "LineString",
                            "coordinates": [
                                [-117.234, 32.8801],
                                [-117.1611, 32.7157],
                            ],
                        }
                    },
                },
                {
                    "distanceMeters": 32187,
                    "duration": "900s",
                },
            ]
        },
    )


def _forbidden_vehicle_provider() -> object:
    """Allow dependency construction but forbid actual catalog access."""

    class ForbiddenCatalogAccess:
        """Fail if any vehicle catalog operation is attempted."""

        def __getattr__(self, name: str) -> object:
            raise AssertionError(
                f"Saved vehicle evaluation must not request catalog specifications: {name}"
            )

    return ForbiddenCatalogAccess()


@pytest.fixture
def postgres_evaluation(
    postgres_engine: Engine,
) -> Iterator[PostgresEvaluationHarness]:
    """Use only the M3-approved disposable local PostgreSQL database."""

    identity_repository = PostgresUserIdentityRepository(
        engine=postgres_engine,
    )
    preferences_repository = PostgresUserPreferencesRepository(
        engine=postgres_engine,
    )
    vehicle_repository = PostgresSavedVehicleRepository(
        engine=postgres_engine,
    )

    owner_identity = _identity("owner")
    other_identity = _identity("other")

    owner = identity_repository.get_or_create_user_id(owner_identity)
    other = identity_repository.get_or_create_user_id(other_identity)

    recorded_requests: list[httpx.Request] = []

    def google_handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return _fake_google_response(
            request,
            recorded_requests,
        )

    verifier = TokenMappingVerifier(
        {
            "owner-token": owner_identity,
            "other-token": other_identity,
        }
    )

    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: verifier
    app.dependency_overrides[get_user_identity_repository] = lambda: identity_repository
    app.dependency_overrides[get_user_preferences_repository] = lambda: preferences_repository
    app.dependency_overrides[get_saved_vehicle_repository] = lambda: vehicle_repository
    app.dependency_overrides[get_google_routes_api_key] = lambda: "integration-test-only-key"
    app.dependency_overrides[get_vehicle_specification_provider] = _forbidden_vehicle_provider

    try:
        with httpx.Client(
            transport=httpx.MockTransport(google_handler),
        ) as google_client:
            app.dependency_overrides[get_google_routes_http_client] = lambda: google_client

            with TestClient(app) as client:
                yield PostgresEvaluationHarness(
                    client=client,
                    owner=owner,
                    other=other,
                    preferences=preferences_repository,
                    vehicles=vehicle_repository,
                    google_requests=recorded_requests,
                )

    finally:
        # The user FK cascades clean up identities, vehicles, and preferences.
        # Never delete or truncate unrelated test database records.
        with postgres_engine.begin() as connection:
            connection.execute(
                delete(users).where(
                    users.c.id.in_(
                        [
                            owner.value,
                            other.value,
                        ]
                    )
                )
            )


def test_persisted_default_profile_evaluates_real_snapshot(
    postgres_evaluation: PostgresEvaluationHarness,
) -> None:
    """Use actual persisted MPG, grade, and VoT through HTTP."""

    harness = postgres_evaluation

    vehicle = _save_gasoline(
        harness,
        harness.owner,
        mpg="31.75",
        grade=GasolineGrade.PREMIUM,
    )

    # Use the real authenticated preferences endpoint to save the default.
    updated = harness.client.patch(
        "/api/v2/preferences",
        headers=_headers(),
        json={
            "value_of_time_per_hour": "0",
            "default_vehicle_id": str(vehicle.id.value),
        },
    )

    assert updated.status_code == 200

    response = harness.client.post(
        _PATH,
        headers=_headers(),
        json=_body(price="5.05"),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["decision"]["candidate_count"] == 2
    assert body["decision"]["eligible_count"] == 2
    assert body["decision"]["missing_data_present"] is False

    assert body["decision"]["recommended_route"]["distance_meters"] == 16093

    first = body["route_evaluations"][0]

    expected_energy_cost = Decimal(16093) / Decimal("1609.344") / Decimal("31.75") * Decimal("5.05")

    assert Decimal(first["energy_estimate"]["cost"]) == expected_energy_cost

    assert Decimal(first["cost_breakdown"]["time_cost"]) == Decimal(0)

    assert first["geometry"]["points"][0] == {
        "latitude": 32.8801,
        "longitude": -117.234,
    }

    # The actual Google Routes adapter makes two acquisitions.
    assert len(harness.google_requests) == 2

    assert all(
        request.headers["X-Goog-Api-Key"] == "integration-test-only-key"
        for request in harness.google_requests
    )


def test_persisted_value_of_time_update_changes_recommendation(
    postgres_evaluation: PostgresEvaluationHarness,
) -> None:
    """A real preference update must change the authoritative decision."""

    harness = postgres_evaluation

    vehicle = _save_gasoline(
        harness,
        harness.owner,
        mpg="25",
    )

    _configure(
        harness,
        harness.owner,
        vehicle,
        value_of_time="0",
    )

    before = harness.client.post(
        _PATH,
        headers=_headers(),
        json=_body(),
    )

    assert before.status_code == 200

    assert before.json()["decision"]["recommended_route"]["distance_meters"] == 16093

    updated = harness.client.patch(
        "/api/v2/preferences",
        headers=_headers(),
        json={
            "value_of_time_per_hour": "40",
        },
    )

    assert updated.status_code == 200

    assert harness.preferences.get_preferences(harness.owner).value_of_time_per_hour == Decimal(40)

    after = harness.client.post(
        _PATH,
        headers=_headers(),
        json=_body(),
    )

    assert after.status_code == 200

    assert after.json()["decision"]["recommended_route"]["distance_meters"] == 32187

    assert after.json()["decision"]["reason"] == "faster_route_worth_extra_cost"

    assert len(harness.google_requests) == 4


def test_postgres_foreign_and_missing_vehicle_ids_are_hidden(
    postgres_evaluation: PostgresEvaluationHarness,
) -> None:
    """Cross-user selection and unknown IDs must be indistinguishable."""

    harness = postgres_evaluation

    owner_vehicle = _save_gasoline(
        harness,
        harness.owner,
    )

    harness.preferences.save_preferences(
        harness.other,
        UserPreferences(
            value_of_time_per_hour=Decimal(25),
        ),
    )

    foreign = harness.client.post(
        _PATH,
        headers=_headers("other-token"),
        json=_body(vehicle_id=owner_vehicle.id.value),
    )

    missing = harness.client.post(
        _PATH,
        headers=_headers("other-token"),
        json=_body(vehicle_id=uuid4()),
    )

    expected = {
        "code": "saved_vehicle_not_found",
        "detail": "Saved vehicle was not found.",
    }

    assert foreign.status_code == 404
    assert missing.status_code == 404

    assert foreign.json() == expected
    assert missing.json() == expected

    # Neither failure may reach Google Routes.
    assert harness.google_requests == []

    # But the actual owner must still be able to use the same snapshot.
    _configure(
        harness,
        harness.owner,
        owner_vehicle,
        value_of_time="25",
    )

    owned = harness.client.post(
        _PATH,
        headers=_headers(),
        json=_body(vehicle_id=owner_vehicle.id.value),
    )

    assert owned.status_code == 200
    assert owned.json()["decision"]["eligible_count"] == 2


def test_deleting_default_clears_selection_but_explicit_vehicle_works(
    postgres_evaluation: PostgresEvaluationHarness,
) -> None:
    """Deleting a default must preserve other owned vehicle snapshots."""

    harness = postgres_evaluation

    deleted_vehicle = _save_gasoline(
        harness,
        harness.owner,
        mpg="25",
    )

    alternate_vehicle = _save_gasoline(
        harness,
        harness.owner,
        mpg="40",
        grade=GasolineGrade.PREMIUM,
    )

    _configure(
        harness,
        harness.owner,
        deleted_vehicle,
        value_of_time="30",
    )

    deleted = harness.client.delete(
        f"/api/v2/vehicles/{deleted_vehicle.id.value}",
        headers=_headers(),
    )

    assert deleted.status_code == 204

    preferences = harness.preferences.get_preferences(harness.owner)

    assert preferences.default_vehicle_id is None
    assert preferences.value_of_time_per_hour == Decimal(30)

    missing_default = harness.client.post(
        _PATH,
        headers=_headers(),
        json=_body(),
    )

    assert missing_default.status_code == 409
    assert missing_default.json()["code"] == ("default_vehicle_not_configured")

    assert harness.google_requests == []

    explicit = harness.client.post(
        _PATH,
        headers=_headers(),
        json=_body(
            vehicle_id=alternate_vehicle.id.value,
            price="5.25",
        ),
    )

    assert explicit.status_code == 200
    assert explicit.json()["decision"]["eligible_count"] == 2

    first_cost = Decimal(explicit.json()["route_evaluations"][0]["energy_estimate"]["cost"])

    expected_cost = Decimal(16093) / Decimal("1609.344") / Decimal(40) * Decimal("5.25")

    assert first_cost == expected_cost


def test_persisted_bev_is_rejected_before_google_routing(
    postgres_evaluation: PostgresEvaluationHarness,
) -> None:
    """A persisted BEV must reject gasoline pricing before routing."""

    harness = postgres_evaluation

    electric_vehicle = harness.vehicles.create_vehicle(
        harness.owner,
        _snapshot(
            ElectricVehicleSpecification(
                combined_kwh_per_mile=Decimal("0.285"),
                city_kwh_per_mile=Decimal("0.250"),
                highway_kwh_per_mile=Decimal("0.320"),
            )
        ),
    )

    _configure(
        harness,
        harness.owner,
        electric_vehicle,
        value_of_time="30",
    )

    response = harness.client.post(
        _PATH,
        headers=_headers(),
        json=_body(),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "energy_input_mismatch"
    assert harness.google_requests == []
