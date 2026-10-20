"""Persisted energy preferences through real HTTP, SQL and trip evaluation."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

import pytest
from browser_server import BrowserCatalog, BrowserPrices, BrowserRoutes
from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from routevalue.api.preferences import get_user_preferences_repository
from routevalue.api.saved_vehicles import (
    get_saved_vehicle_repository,
    get_vehicle_specification_provider,
)
from routevalue.api.terrain_v2_composition import build_terrain_v2_evaluation_service
from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import get_profile_driven_trip_evaluation_service
from routevalue.application.gasoline_price_geography import PricingJurisdictionResult
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.models import ResolvedLocation
from routevalue.application.preferences import PreferredFuelMarket
from routevalue.domain.identity import UserId
from routevalue.infrastructure.persistence.saved_vehicles import PostgresSavedVehicleRepository
from routevalue.infrastructure.persistence.schema import users
from routevalue.infrastructure.persistence.user_preferences import PostgresUserPreferencesRepository
from routevalue.infrastructure.pricing.census_resolver_lifecycle import (
    get_census_pricing_jurisdiction_resolver,
)
from routevalue.main import create_app

PATH = "/api/v2/preferences"
MARKET = {"display_name": "Raleigh, NC", "latitude": 35.7796, "longitude": -78.6382}
TRIP = {
    "origin": {"display_name": "San Diego", "latitude": 32.7157, "longitude": -117.1611},
    "destination": {"display_name": "Julian", "latitude": 33.0787, "longitude": -116.6019},
}


class RecordingJurisdiction:
    def __init__(self) -> None:
        self.calls: list[ResolvedLocation] = []

    def resolve(self, location: ResolvedLocation) -> PricingJurisdictionResult:
        self.calls.append(location)
        return get_census_pricing_jurisdiction_resolver().resolve(location)


@dataclass
class Harness:
    engine: Engine
    client: TestClient
    owner: UserId
    other: UserId
    resolver: RecordingJurisdiction

    def headers(self, *, other: bool = False) -> dict[str, str]:
        return {"X-Test-User": str((self.other if other else self.owner).value)}

    def patch(self, body: dict[str, object], *, other: bool = False) -> dict[str, object]:
        response = self.client.patch(PATH, json=body, headers=self.headers(other=other))
        assert response.status_code == 200, response.text
        return dict(response.json())

    def vehicle(self, *, electric: bool = True) -> str:
        model = "Electric" if electric else "Gasoline"
        response = self.client.post(
            "/api/v2/vehicles",
            headers=self.headers(),
            json={
                "year": 2025,
                "make": "Example",
                "model": model,
                "configuration": "Standard",
                "source": "browser_fixture",
                "source_id": model,
            },
        )
        assert response.status_code == 201, response.text
        identifier = str(response.json()["id"])
        self.patch({"default_vehicle_id": identifier, "value_of_time_per_hour": "24"})
        return identifier


@pytest.fixture
def harness(postgres_engine: Engine) -> Iterator[Harness]:
    owner, other = UserId(uuid4()), UserId(uuid4())
    with postgres_engine.begin() as connection:
        connection.execute(insert(users), [{"id": owner.value}, {"id": other.value}])
    preferences = PostgresUserPreferencesRepository(engine=postgres_engine)
    vehicles = PostgresSavedVehicleRepository(engine=postgres_engine)
    resolver = RecordingJurisdiction()
    app = create_app()

    def identity(x_test_user: Annotated[str, Header()]) -> AuthenticatedUser:
        return AuthenticatedUser(user_id=UserId(UUID(x_test_user)))

    app.dependency_overrides[get_authenticated_user] = identity
    app.dependency_overrides[get_user_preferences_repository] = lambda: preferences
    app.dependency_overrides[get_saved_vehicle_repository] = lambda: vehicles
    app.dependency_overrides[get_vehicle_specification_provider] = BrowserCatalog
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: (
        build_terrain_v2_evaluation_service(
            preferences_repository=preferences,
            saved_vehicle_repository=vehicles,
            route_provider=BrowserRoutes(),
            gasoline_price_provider=BrowserPrices(missing=False),
            gasoline_jurisdiction_resolver=resolver,
            pricing_clock=lambda: datetime(2026, 10, 19, 12, tzinfo=UTC),
        )
    )
    try:
        with TestClient(app) as client:
            yield Harness(postgres_engine, client, owner, other, resolver)
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(delete(users).where(users.c.id.in_([owner.value, other.value])))


def test_rate_survives_repository_recreation_and_drives_ev_without_trip_input(
    harness: Harness,
) -> None:
    vehicle = harness.vehicle()
    harness.patch({"electricity_price_per_kwh": "0.275123456789"})
    reloaded = PostgresUserPreferencesRepository(engine=harness.engine).get_preferences(
        harness.owner
    )
    assert reloaded.electricity_price_per_kwh == Decimal("0.275123456789")
    assert (
        str(reloaded.default_vehicle_id.value) == vehicle if reloaded.default_vehicle_id else False
    )
    response = harness.client.post("/api/v2/trip-evaluations", json=TRIP, headers=harness.headers())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["energy_price"] == {
        "energy_type": "electricity",
        "price_per_kilowatt_hour": "0.275123456789",
        "source": "user_preference",
    }
    energy = result["route_evaluations"][0]["energy_estimate"]
    assert Decimal(energy["cost"]) == Decimal(energy["consumption"]["kilowatt_hours"]) * Decimal(
        "0.275123456789"
    )
    assert harness.resolver.calls == []


def test_ev_override_does_not_mutate_saved_rate_and_clear_requires_explicit_input(
    harness: Harness,
) -> None:
    harness.vehicle()
    harness.patch({"electricity_price_per_kwh": "0.25"})
    override = {**TRIP, "electricity": {"price_per_kilowatt_hour": "0"}}
    response = harness.client.post(
        "/api/v2/trip-evaluations", json=override, headers=harness.headers()
    )
    assert response.status_code == 200
    assert response.json()["energy_price"]["source"] == "user_input"
    assert Decimal(response.json()["route_evaluations"][0]["energy_estimate"]["cost"]) == 0
    assert (
        harness.client.get(PATH, headers=harness.headers()).json()["electricity_price_per_kwh"]
        == "0.25"
    )
    harness.patch({"electricity_price_per_kwh": None})
    response = harness.client.post("/api/v2/trip-evaluations", json=TRIP, headers=harness.headers())
    assert response.status_code == 409
    assert response.json()["code"] == "electricity_price_not_configured"
    assert (
        harness.client.post(
            "/api/v2/trip-evaluations", json=override, headers=harness.headers()
        ).status_code
        == 200
    )


def test_zero_saved_rate_is_not_treated_as_unset(harness: Harness) -> None:
    harness.vehicle()
    harness.patch({"electricity_price_per_kwh": "0"})
    response = harness.client.post("/api/v2/trip-evaluations", json=TRIP, headers=harness.headers())
    assert response.status_code == 200
    assert response.json()["energy_price"]["source"] == "user_preference"
    assert Decimal(response.json()["route_evaluations"][0]["energy_estimate"]["cost"]) == 0


def test_stored_rate_never_accepts_a_gasoline_price_for_an_ev(harness: Harness) -> None:
    harness.vehicle()
    harness.patch({"electricity_price_per_kwh": "0.25"})
    response = harness.client.post(
        "/api/v2/trip-evaluations",
        json={**TRIP, "gasoline": {"fuel_price_per_gallon": "4"}},
        headers=harness.headers(),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "energy_input_mismatch"


def test_unsupported_market_fails_honestly_and_manual_price_bypasses_lookup(
    harness: Harness,
) -> None:
    harness.vehicle(electric=False)
    market = {"display_name": "Unsupported purchasing area", "latitude": 0.0, "longitude": 0.0}
    harness.patch({"preferred_fuel_market": market})
    response = harness.client.post("/api/v2/trip-evaluations", json=TRIP, headers=harness.headers())
    assert response.status_code == 409
    assert response.json()["code"] == "gasoline_price_unavailable"
    lookups = len(harness.resolver.calls)
    response = harness.client.post(
        "/api/v2/trip-evaluations",
        json={**TRIP, "gasoline": {"fuel_price_per_gallon": "4.75"}},
        headers=harness.headers(),
    )
    assert response.status_code == 200
    assert response.json()["energy_price"]["source"] == "user_override"
    assert len(harness.resolver.calls) == lookups
    assert (
        harness.client.get(PATH, headers=harness.headers()).json()["preferred_fuel_market"]
        == market
    )


def test_preferred_area_overrides_origin_then_clear_restores_origin_with_real_geography(
    harness: Harness,
) -> None:
    harness.vehicle(electric=False)
    harness.patch({"preferred_fuel_market": MARKET})
    reloaded = PostgresUserPreferencesRepository(engine=harness.engine).get_preferences(
        harness.owner
    )
    assert reloaded.preferred_fuel_market == PreferredFuelMarket("Raleigh, NC", 35.7796, -78.6382)
    # A misleading label must never select California pricing for NC coordinates.
    harness.patch({"preferred_fuel_market": {**MARKET, "display_name": "California"}})
    response = harness.client.post("/api/v2/trip-evaluations", json=TRIP, headers=harness.headers())
    assert response.status_code == 200, response.text
    assert response.json()["energy_price"]["geography"] != "California"
    assert harness.resolver.calls[-1].longitude == -78.6382
    harness.patch({"preferred_fuel_market": None})
    response = harness.client.post("/api/v2/trip-evaluations", json=TRIP, headers=harness.headers())
    assert response.status_code == 200
    assert response.json()["energy_price"]["geography"] == "California"
    assert harness.resolver.calls[-1].longitude == -117.1611


def test_sparse_updates_default_delete_and_other_account_preserve_energy_preferences(
    harness: Harness,
) -> None:
    vehicle = harness.vehicle()
    harness.patch({"electricity_price_per_kwh": "0.25", "preferred_fuel_market": MARKET})
    updated = harness.patch({"value_of_time_per_hour": "30", "default_vehicle_id": None})
    assert updated["electricity_price_per_kwh"] == "0.25"
    assert updated["preferred_fuel_market"] == MARKET
    harness.patch({"default_vehicle_id": vehicle})
    assert (
        harness.client.delete(f"/api/v2/vehicles/{vehicle}", headers=harness.headers()).status_code
        == 204
    )
    current = harness.client.get(PATH, headers=harness.headers()).json()
    assert current["default_vehicle_id"] is None
    assert current["electricity_price_per_kwh"] == "0.25"
    assert current["preferred_fuel_market"] == MARKET
    other = harness.client.get(PATH, headers=harness.headers(other=True)).json()
    assert other["electricity_price_per_kwh"] is None
    assert other["preferred_fuel_market"] is None
    harness.patch({"electricity_price_per_kwh": "0.99", "preferred_fuel_market": None}, other=True)
    assert harness.client.get(PATH, headers=harness.headers()).json() == current


@pytest.mark.parametrize("rate", ["-0.01", "NaN", "Infinity", "-Infinity", "abc", True])
def test_invalid_rates_are_rejected_without_changing_other_preferences(
    harness: Harness, rate: object
) -> None:
    before = harness.patch({"value_of_time_per_hour": "24", "preferred_fuel_market": MARKET})
    response = harness.client.patch(
        PATH,
        json={"electricity_price_per_kwh": rate, "value_of_time_per_hour": "99"},
        headers=harness.headers(),
    )
    assert response.status_code == 422
    assert harness.client.get(PATH, headers=harness.headers()).json() == before


@pytest.mark.parametrize(
    "market",
    [
        {"display_name": "", "latitude": 35, "longitude": -78},
        {"display_name": "Raleigh", "latitude": 91, "longitude": -78},
        {"display_name": "Raleigh", "latitude": True, "longitude": -78},
        {"display_name": "Raleigh", "latitude": 35},
        {**MARKET, "region_id": "SCA"},
        {**MARKET, "user_id": str(uuid4())},
    ],
)
def test_invalid_or_spoofed_market_is_rejected(harness: Harness, market: dict[str, object]) -> None:
    before = harness.patch({"electricity_price_per_kwh": "0.25"})
    assert (
        harness.client.patch(
            PATH, json={"preferred_fuel_market": market}, headers=harness.headers()
        ).status_code
        == 422
    )
    assert harness.client.get(PATH, headers=harness.headers()).json() == before


@pytest.mark.parametrize("rate", ["-1", "NaN", "Infinity", "-Infinity"])
def test_database_also_rejects_invalid_rate(harness: Harness, rate: str) -> None:
    with pytest.raises(IntegrityError), harness.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.user_preferences (user_id, electricity_price_per_kwh) VALUES (:id, CAST(:rate AS numeric))"
            ),
            {"id": harness.owner.value, "rate": rate},
        )
