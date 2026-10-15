"""M5 integration tests: authenticated BEV evaluation with real local PostgreSQL."""

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
from routevalue.application.saved_vehicles import SavedVehicle, SavedVehicleSnapshot
from routevalue.domain.identity import UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    VehicleEnergySpecification,
)
from routevalue.infrastructure.persistence.saved_vehicles import PostgresSavedVehicleRepository
from routevalue.infrastructure.persistence.schema import users
from routevalue.infrastructure.persistence.user_identity import PostgresUserIdentityRepository
from routevalue.infrastructure.persistence.user_preferences import PostgresUserPreferencesRepository
from routevalue.main import create_app

_PATH = "/api/v2/trip-evaluations"


class TokenVerifier:
    """Authenticate two deterministic test bearer tokens."""

    def __init__(self, identities: dict[str, VerifiedExternalIdentity]) -> None:
        self.identities = identities

    def verify_token(self, token: str) -> VerifiedExternalIdentity:
        identity = self.identities.get(token)
        if identity is None:
            raise InvalidAuthenticationError
        return identity


@dataclass(slots=True)
class ElectricPostgresHarness:
    client: TestClient
    owner: UserId
    other: UserId
    preferences: PostgresUserPreferencesRepository
    vehicles: PostgresSavedVehicleRepository
    google_requests: list[httpx.Request]
    google_status: list[int]


def _headers(token: str = "owner-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _body(
    *,
    vehicle_id: UUID | None = None,
    electricity: str | None = "0.3157",
    gasoline: str | None = None,
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
    }
    if vehicle_id is not None:
        body["saved_vehicle_id"] = str(vehicle_id)
    if electricity is not None:
        body["electricity"] = {"price_per_kilowatt_hour": electricity}
    if gasoline is not None:
        body["gasoline"] = {"fuel_price_per_gallon": gasoline}
    return body


def _snapshot(
    specification: VehicleEnergySpecification,
) -> SavedVehicleSnapshot:
    return SavedVehicleSnapshot(
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Integration",
            model="Test Vehicle",
            configuration="Baseline",
            source="fueleconomy_gov",
            source_id=uuid4().hex,
        ),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 12, tzinfo=UTC),
    )


def _save_bev(
    harness: ElectricPostgresHarness,
    user_id: UserId,
    *,
    kwh_per_mile: str = "0.285",
) -> SavedVehicle:
    return harness.vehicles.create_vehicle(
        user_id,
        _snapshot(
            ElectricVehicleSpecification(
                combined_kwh_per_mile=Decimal(kwh_per_mile),
                city_kwh_per_mile=Decimal("0.250"),
                highway_kwh_per_mile=Decimal("0.320"),
            )
        ),
    )


def _save_gasoline(
    harness: ElectricPostgresHarness,
    user_id: UserId,
) -> SavedVehicle:
    return harness.vehicles.create_vehicle(
        user_id,
        _snapshot(
            GasolineVehicleSpecification(
                combined_mpg=Decimal(25),
                fuel_grade=GasolineGrade.REGULAR,
            )
        ),
    )


def _configure(
    harness: ElectricPostgresHarness,
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


def _fake_google_response() -> httpx.Response:
    """Two distinct alternatives; first includes provider geometry."""
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
                {"distanceMeters": 32187, "duration": "900s"},
            ]
        },
    )


def _forbidden_catalog() -> object:
    class ForbiddenCatalog:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"Saved evaluation attempted catalog lookup: {name}")

    return ForbiddenCatalog()


@pytest.fixture
def electric_postgres(
    postgres_engine: Engine,
) -> Iterator[ElectricPostgresHarness]:
    """Exercise real local repositories with a mocked Google HTTP transport."""
    identities = PostgresUserIdentityRepository(engine=postgres_engine)
    preferences = PostgresUserPreferencesRepository(engine=postgres_engine)
    vehicles = PostgresSavedVehicleRepository(engine=postgres_engine)

    owner_identity = VerifiedExternalIdentity(
        issuer="https://routevalue-m5.example.test",
        subject=f"owner-{uuid4().hex}",
    )
    other_identity = VerifiedExternalIdentity(
        issuer="https://routevalue-m5.example.test",
        subject=f"other-{uuid4().hex}",
    )
    owner = identities.get_or_create_user_id(owner_identity)
    other = identities.get_or_create_user_id(other_identity)
    requests: list[httpx.Request] = []
    status = [200]

    def google_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if status[0] != 200:
            return httpx.Response(status_code=status[0])
        return _fake_google_response()

    verifier = TokenVerifier(
        {
            "owner-token": owner_identity,
            "other-token": other_identity,
        }
    )
    app = create_app()
    app.dependency_overrides[get_authentication_verifier] = lambda: verifier
    app.dependency_overrides[get_user_identity_repository] = lambda: identities
    app.dependency_overrides[get_user_preferences_repository] = lambda: preferences
    app.dependency_overrides[get_saved_vehicle_repository] = lambda: vehicles
    app.dependency_overrides[get_google_routes_api_key] = lambda: "m5-local-test-key"
    app.dependency_overrides[get_vehicle_specification_provider] = _forbidden_catalog

    try:
        with httpx.Client(transport=httpx.MockTransport(google_handler)) as google_client:
            app.dependency_overrides[get_google_routes_http_client] = lambda: google_client
            with TestClient(app) as client:
                yield ElectricPostgresHarness(
                    client=client,
                    owner=owner,
                    other=other,
                    preferences=preferences,
                    vehicles=vehicles,
                    google_requests=requests,
                    google_status=status,
                )
    finally:
        # Delete only identities created for this test; FK cascade handles their data.
        with postgres_engine.begin() as connection:
            connection.execute(delete(users).where(users.c.id.in_([owner.value, other.value])))


def test_persisted_bev_uses_saved_efficiency_and_mocked_routes(
    electric_postgres: ElectricPostgresHarness,
) -> None:
    harness = electric_postgres
    vehicle = _save_bev(harness, harness.owner)
    _configure(harness, harness.owner, vehicle)

    response = harness.client.post(_PATH, headers=_headers(), json=_body())

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["eligible_count"] == 2
    assert body["decision"]["recommended_route"]["distance_meters"] == 16093
    assert body["decision"]["missing_data_present"] is False

    first = body["route_evaluations"][0]
    consumption = first["energy_estimate"]["consumption"]
    expected_kwh = Decimal(16093) / Decimal("1609.344") * Decimal("0.285")
    assert consumption["energy_type"] == "electricity"
    assert Decimal(consumption["kilowatt_hours"]) == expected_kwh
    assert Decimal(first["energy_estimate"]["cost"]) == expected_kwh * Decimal("0.3157")
    assert Decimal(first["cost_breakdown"]["monetary_cost"]) == (expected_kwh * Decimal("0.3157"))
    assert first["geometry"]["points"][0] == {
        "latitude": 32.8801,
        "longitude": -117.234,
    }
    assert len(harness.google_requests) == 2
    assert all(
        request.headers["X-Goog-Api-Key"] == "m5-local-test-key"
        for request in harness.google_requests
    )


def test_persisted_bev_value_of_time_changes_authoritative_decision(
    electric_postgres: ElectricPostgresHarness,
) -> None:
    harness = electric_postgres
    vehicle = _save_bev(harness, harness.owner)
    _configure(harness, harness.owner, vehicle)

    before = harness.client.post(_PATH, headers=_headers(), json=_body())
    assert before.status_code == 200
    assert before.json()["decision"]["recommended_route"]["distance_meters"] == 16093

    updated = harness.client.patch(
        "/api/v2/preferences",
        headers=_headers(),
        json={"value_of_time_per_hour": "40"},
    )
    assert updated.status_code == 200

    after = harness.client.post(_PATH, headers=_headers(), json=_body())
    assert after.status_code == 200
    assert after.json()["decision"]["recommended_route"]["distance_meters"] == 32187
    assert after.json()["decision"]["reason"] == "faster_route_worth_extra_cost"
    assert len(harness.google_requests) == 4


def test_explicit_owned_bev_overrides_gasoline_default(
    electric_postgres: ElectricPostgresHarness,
) -> None:
    harness = electric_postgres
    gasoline = _save_gasoline(harness, harness.owner)
    bev = _save_bev(harness, harness.owner, kwh_per_mile="0.350")
    _configure(harness, harness.owner, gasoline)

    response = harness.client.post(
        _PATH,
        headers=_headers(),
        json=_body(vehicle_id=bev.id.value),
    )
    assert response.status_code == 200
    energy = response.json()["route_evaluations"][0]["energy_estimate"]
    assert energy["consumption"]["energy_type"] == "electricity"
    expected_kwh = Decimal(16093) / Decimal("1609.344") * Decimal("0.350")
    assert Decimal(energy["consumption"]["kilowatt_hours"]) == expected_kwh
    assert len(harness.google_requests) == 2


def test_foreign_and_unknown_bev_ids_return_identical_404(
    electric_postgres: ElectricPostgresHarness,
) -> None:
    harness = electric_postgres
    bev = _save_bev(harness, harness.owner)
    harness.preferences.save_preferences(
        harness.other,
        UserPreferences(value_of_time_per_hour=Decimal(25)),
    )
    foreign = harness.client.post(
        _PATH,
        headers=_headers("other-token"),
        json=_body(vehicle_id=bev.id.value),
    )
    unknown = harness.client.post(
        _PATH,
        headers=_headers("other-token"),
        json=_body(vehicle_id=uuid4()),
    )
    expected = {
        "code": "saved_vehicle_not_found",
        "detail": "Saved vehicle was not found.",
    }
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json() == expected
    assert harness.google_requests == []


@pytest.mark.parametrize("invalid_token", [None, "bad-token"])
def test_bev_evaluation_requires_valid_authentication(
    electric_postgres: ElectricPostgresHarness,
    invalid_token: str | None,
) -> None:
    harness = electric_postgres
    bev = _save_bev(harness, harness.owner)
    _configure(harness, harness.owner, bev)
    headers = _headers(invalid_token) if invalid_token is not None else {}
    response = harness.client.post(_PATH, headers=headers, json=_body())
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert harness.google_requests == []


@pytest.mark.parametrize(
    ("bad_body", "expected_status"),
    [
        (_body(electricity=None), 409),
        (_body(electricity="0.31", gasoline="4.50"), 422),
        (_body(electricity="-0.01"), 422),
        (_body(electricity="NaN"), 422),
    ],
)
def test_invalid_electricity_contract_fails_before_google(
    electric_postgres: ElectricPostgresHarness,
    bad_body: dict[str, object],
    expected_status: int,
) -> None:
    harness = electric_postgres
    bev = _save_bev(harness, harness.owner)
    _configure(harness, harness.owner, bev)

    response = harness.client.post(
        _PATH,
        headers=_headers(),
        json=bad_body,
    )

    assert response.status_code == expected_status

    if expected_status == 409:
        assert response.json()["code"] == "energy_input_mismatch"

    assert harness.google_requests == []


@pytest.mark.parametrize("powertrain", ["bev", "gasoline"])
def test_wrong_energy_price_is_a_safe_409(
    electric_postgres: ElectricPostgresHarness,
    powertrain: str,
) -> None:
    harness = electric_postgres
    vehicle = (
        _save_bev(harness, harness.owner)
        if powertrain == "bev"
        else _save_gasoline(harness, harness.owner)
    )
    _configure(harness, harness.owner, vehicle)
    body = (
        _body(electricity=None, gasoline="4.50")
        if powertrain == "bev"
        else _body(electricity="0.31")
    )
    response = harness.client.post(_PATH, headers=_headers(), json=body)
    assert response.status_code == 409
    assert response.json() == {
        "code": "energy_input_mismatch",
        "detail": "The energy price type does not match the selected vehicle.",
    }
    assert harness.google_requests == []


def test_zero_electricity_price_does_not_mean_missing_data(
    electric_postgres: ElectricPostgresHarness,
) -> None:
    harness = electric_postgres
    bev = _save_bev(harness, harness.owner)
    _configure(harness, harness.owner, bev)
    response = harness.client.post(
        _PATH,
        headers=_headers(),
        json=_body(electricity="0"),
    )
    assert response.status_code == 200
    energy = response.json()["route_evaluations"][0]["energy_estimate"]
    assert Decimal(energy["cost"]) == Decimal(0)
    assert Decimal(energy["consumption"]["kilowatt_hours"]) > 0
    assert response.json()["decision"]["missing_data_present"] is False


def test_google_routes_failure_for_bev_is_sanitized(
    electric_postgres: ElectricPostgresHarness,
) -> None:
    harness = electric_postgres
    bev = _save_bev(harness, harness.owner)
    _configure(harness, harness.owner, bev)
    harness.google_status[0] = 503

    response = harness.client.post(_PATH, headers=_headers(), json=_body())
    assert response.status_code == 503
    assert response.json()["code"] == "routing_service_unavailable"
    assert "m5-local-test-key" not in response.text
    assert harness.google_requests
