"""M10 acceptance: concurrent HTTP updates against real PostgreSQL persistence."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from test_api_preferences_postgres import _client, _create_saved_vehicle, _create_user
from test_postgres_user_preferences_repository import _delete_user

from routevalue.application.preferences import (
    PreferredFuelMarket,
    UserPreferences,
    UserPreferencesPatch,
)
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.infrastructure.persistence.saved_vehicles import PostgresSavedVehicleRepository
from routevalue.infrastructure.persistence.schema import user_preferences
from routevalue.infrastructure.persistence.user_preferences import PostgresUserPreferencesRepository


@pytest.mark.parametrize("existing", [False, True])
def test_simultaneous_http_patches_preserve_every_field(
    postgres_engine: Engine, existing: bool
) -> None:
    owner = _create_user(postgres_engine)
    barrier = Barrier(2, timeout=10)

    class ConcurrentRepository(PostgresUserPreferencesRepository):
        def update_preferences(
            self, user_id: UserId, changes: UserPreferencesPatch
        ) -> UserPreferences:
            barrier.wait()
            return super().update_preferences(user_id, changes)

    repository = ConcurrentRepository(engine=postgres_engine)
    market = PreferredFuelMarket("Raleigh", 35.7796, -78.6382) if existing else None
    if existing:
        repository.save_preferences(owner, UserPreferences(preferred_fuel_market=market))
    vehicles = PostgresSavedVehicleRepository(engine=postgres_engine)
    try:

        def patch(body: dict[str, object]) -> int:
            with _client(
                user_id=owner, preferences_repository=repository, vehicle_repository=vehicles
            ) as client:
                return int(client.patch("/api/v2/preferences", json=body).status_code)

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(patch, {"value_of_time_per_hour": "24.125"})
            second = executor.submit(patch, {"electricity_price_per_kwh": "0.275"})
            assert first.result(timeout=15) == second.result(timeout=15) == 200
        assert repository.get_preferences(owner) == UserPreferences(
            value_of_time_per_hour=Decimal("24.125"),
            electricity_price_per_kwh=Decimal("0.275"),
            preferred_fuel_market=market,
        )
    finally:
        _delete_user(postgres_engine, owner)


def test_interleaved_update_does_not_overwrite_market_or_resurrect_deleted_default(
    postgres_engine: Engine,
) -> None:
    owner = _create_user(postgres_engine)
    vehicle = SavedVehicleId(_create_saved_vehicle(postgres_engine, owner))
    plain = PostgresUserPreferencesRepository(engine=postgres_engine)
    vehicles = PostgresSavedVehicleRepository(engine=postgres_engine)
    market = PreferredFuelMarket("Raleigh", 35.7796, -78.6382)
    plain.save_preferences(owner, UserPreferences(default_vehicle_id=vehicle))

    class InterleavedRepository(PostgresUserPreferencesRepository):
        def interleave(self) -> None:
            plain.update_preferences(owner, {"preferred_fuel_market": market})
            assert vehicles.delete_vehicle(owner, vehicle)

        def save_preferences(
            self, user_id: UserId, preferences: UserPreferences
        ) -> UserPreferences:
            self.interleave()
            return super().save_preferences(user_id, preferences)

        def update_preferences(
            self, user_id: UserId, changes: UserPreferencesPatch
        ) -> UserPreferences:
            self.interleave()
            return super().update_preferences(user_id, changes)

    try:
        with _client(
            user_id=owner,
            preferences_repository=InterleavedRepository(engine=postgres_engine),
            vehicle_repository=vehicles,
        ) as client:
            response = client.patch(
                "/api/v2/preferences", json={"electricity_price_per_kwh": "0.25"}
            )
        assert response.status_code == 200
        assert plain.get_preferences(owner) == UserPreferences(
            electricity_price_per_kwh=Decimal("0.25"), preferred_fuel_market=market
        )
    finally:
        _delete_user(postgres_engine, owner)


def test_delete_after_ownership_validation_returns_404_and_rolls_back_all_fields(
    postgres_engine: Engine,
) -> None:
    owner = _create_user(postgres_engine)
    vehicle = SavedVehicleId(_create_saved_vehicle(postgres_engine, owner))
    repository = PostgresUserPreferencesRepository(engine=postgres_engine)
    repository.save_preferences(owner, UserPreferences(electricity_price_per_kwh=Decimal("0.2")))

    class DeletingRepository(PostgresSavedVehicleRepository):
        def get_vehicle(self, user_id: UserId, vehicle_id: SavedVehicleId) -> SavedVehicle | None:
            found = super().get_vehicle(user_id, vehicle_id)
            assert self.delete_vehicle(user_id, vehicle_id)
            return found

    try:
        with _client(
            user_id=owner,
            preferences_repository=repository,
            vehicle_repository=DeletingRepository(engine=postgres_engine),
        ) as client:
            response = client.patch(
                "/api/v2/preferences",
                json={"default_vehicle_id": str(vehicle.value), "electricity_price_per_kwh": "0.9"},
            )
        assert response.status_code == 404
        assert response.json()["code"] == "saved_vehicle_not_found"
        assert repository.get_preferences(owner) == UserPreferences(
            electricity_price_per_kwh=Decimal("0.2")
        )
    finally:
        _delete_user(postgres_engine, owner)


def test_repeated_patch_is_noop_but_explicit_null_clears(postgres_engine: Engine) -> None:
    owner = _create_user(postgres_engine)
    repository = PostgresUserPreferencesRepository(engine=postgres_engine)
    try:
        repository.update_preferences(owner, {"electricity_price_per_kwh": Decimal(0)})

        def timestamp() -> object:
            with postgres_engine.connect() as connection:
                return connection.execute(
                    select(user_preferences.c.updated_at).where(
                        user_preferences.c.user_id == owner.value
                    )
                ).scalar_one()

        before = timestamp()
        repository.update_preferences(owner, {"electricity_price_per_kwh": Decimal(0)})
        assert timestamp() == before
        repository.update_preferences(owner, {"value_of_time_per_hour": Decimal(30)})
        repository.update_preferences(owner, {"electricity_price_per_kwh": None})
        assert repository.get_preferences(owner) == UserPreferences(
            value_of_time_per_hour=Decimal(30)
        )
    finally:
        _delete_user(postgres_engine, owner)
