"""HTTP-to-PostgreSQL integration for authenticated V2 preferences."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import Engine

from routevalue.api.errors import (
    SavedVehicleNotFoundError,
    saved_vehicle_not_found_error_handler,
)
from routevalue.api.preferences import (
    get_user_preferences_repository,
    router,
)
from routevalue.api.saved_vehicles import (
    get_saved_vehicle_repository,
)
from routevalue.api.user_identity import (
    get_authenticated_user,
)
from routevalue.application.identity import (
    AuthenticatedUser,
)
from routevalue.domain.identity import (
    UserId,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    PostgresSavedVehicleRepository,
)
from routevalue.infrastructure.persistence.schema import (
    saved_vehicles,
    user_preferences,
    users,
)
from routevalue.infrastructure.persistence.user_preferences import (
    PostgresUserPreferencesRepository,
)


def _create_user(
    engine: Engine,
) -> UserId:
    user_id = UserId(value=uuid4())

    with engine.begin() as connection:
        connection.execute(insert(users).values(id=user_id.value))

    return user_id


def _create_saved_vehicle(
    engine: Engine,
    user_id: UserId,
) -> UUID:
    vehicle_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            insert(saved_vehicles).values(
                id=vehicle_id,
                user_id=user_id.value,
                year=2025,
                make="Toyota",
                model="Camry",
                configuration=("Gasoline configuration"),
                source="fueleconomy.gov",
                source_id=(f"test-{uuid4().hex}"),
                specification_retrieved_at=(datetime.now(UTC)),
                powertrain="gasoline",
                gasoline_grade="regular",
                combined_mpg=Decimal("32.125"),
                city_mpg=Decimal("28.5"),
                highway_mpg=Decimal("38.25"),
            )
        )

    return vehicle_id


def _client(
    *,
    user_id: UserId,
    preferences_repository: (PostgresUserPreferencesRepository),
    vehicle_repository: (PostgresSavedVehicleRepository),
) -> TestClient:
    app = FastAPI()

    app.include_router(router)

    app.add_exception_handler(
        SavedVehicleNotFoundError,
        saved_vehicle_not_found_error_handler,
    )

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)

    app.dependency_overrides[get_user_preferences_repository] = lambda: preferences_repository

    app.dependency_overrides[get_saved_vehicle_repository] = lambda: vehicle_repository

    return TestClient(app)


def test_authenticated_preferences_round_trip_through_postgres(
    postgres_engine: Engine,
) -> None:
    user_id = _create_user(postgres_engine)

    vehicle_id = _create_saved_vehicle(
        postgres_engine,
        user_id,
    )

    preferences_repository = PostgresUserPreferencesRepository(
        engine=postgres_engine,
    )

    vehicle_repository = PostgresSavedVehicleRepository(
        engine=postgres_engine,
    )

    client = _client(
        user_id=user_id,
        preferences_repository=(preferences_repository),
        vehicle_repository=(vehicle_repository),
    )

    try:
        initial = client.get("/api/v2/preferences")

        assert initial.status_code == 200

        assert initial.json() == {
            "value_of_time_per_hour": None,
            "default_vehicle_id": None,
        }

        updated = client.patch(
            "/api/v2/preferences",
            json={
                "value_of_time_per_hour": ("33.123456789"),
                "default_vehicle_id": (str(vehicle_id)),
            },
        )

        assert updated.status_code == 200

        assert updated.json() == {
            "value_of_time_per_hour": ("33.123456789"),
            "default_vehicle_id": (str(vehicle_id)),
        }

        reloaded = client.get("/api/v2/preferences")

        assert reloaded.status_code == 200
        assert reloaded.json() == updated.json()

        with postgres_engine.connect() as connection:
            stored = (
                connection.execute(
                    select(
                        user_preferences.c.value_of_time_per_hour,
                        user_preferences.c.default_vehicle_id,
                    ).where(user_preferences.c.user_id == user_id.value)
                )
                .mappings()
                .one()
            )

        assert stored["value_of_time_per_hour"] == Decimal("33.123456789")

        assert stored["default_vehicle_id"] == vehicle_id

    finally:
        with postgres_engine.begin() as connection:
            connection.execute(delete(users).where(users.c.id == user_id.value))


def test_foreign_default_vehicle_is_hidden_and_update_is_atomic(
    postgres_engine: Engine,
) -> None:
    authenticated_user = _create_user(postgres_engine)

    other_user = _create_user(postgres_engine)

    foreign_vehicle_id = _create_saved_vehicle(
        postgres_engine,
        other_user,
    )

    preferences_repository = PostgresUserPreferencesRepository(
        engine=postgres_engine,
    )

    vehicle_repository = PostgresSavedVehicleRepository(
        engine=postgres_engine,
    )

    client = _client(
        user_id=authenticated_user,
        preferences_repository=(preferences_repository),
        vehicle_repository=(vehicle_repository),
    )

    try:
        response = client.patch(
            "/api/v2/preferences",
            json={
                "value_of_time_per_hour": "99",
                "default_vehicle_id": (str(foreign_vehicle_id)),
            },
        )

        assert response.status_code == 404

        assert response.json() == {
            "code": ("saved_vehicle_not_found"),
            "detail": ("Saved vehicle was not found."),
        }

        with postgres_engine.connect() as connection:
            row_count = connection.execute(
                select(func.count())
                .select_from(user_preferences)
                .where(user_preferences.c.user_id == authenticated_user.value)
            ).scalar_one()

        assert row_count == 0

    finally:
        with postgres_engine.begin() as connection:
            connection.execute(
                delete(users).where(
                    users.c.id.in_(
                        [
                            authenticated_user.value,
                            other_user.value,
                        ]
                    )
                )
            )
