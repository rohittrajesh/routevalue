"""HTTP-to-PostgreSQL integration for authenticated V2 preferences."""

from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Engine

from routevalue.api.preferences import (
    get_user_preferences_repository,
    router,
)
from routevalue.api.user_identity import (
    get_authenticated_user,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.domain.identity import UserId
from routevalue.infrastructure.persistence.schema import (
    user_preferences,
    users,
)
from routevalue.infrastructure.persistence.user_preferences import (
    PostgresUserPreferencesRepository,
)


def test_authenticated_preferences_round_trip_through_postgres(
    postgres_engine: Engine,
) -> None:
    user_id = UserId(value=uuid4())

    with postgres_engine.begin() as connection:
        connection.execute(insert(users).values(id=user_id.value))

    repository = PostgresUserPreferencesRepository(
        engine=postgres_engine,
    )

    app = FastAPI()

    app.include_router(router)

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)

    app.dependency_overrides[get_user_preferences_repository] = lambda: repository

    client = TestClient(app)

    try:
        initial = client.get("/api/v2/preferences")

        assert initial.status_code == 200
        assert initial.json() == {
            "value_of_time_per_hour": None,
        }

        updated = client.patch(
            "/api/v2/preferences",
            json={
                "value_of_time_per_hour": ("33.123456789"),
            },
        )

        assert updated.status_code == 200
        assert updated.json() == {
            "value_of_time_per_hour": ("33.123456789"),
        }

        reloaded = client.get("/api/v2/preferences")

        assert reloaded.status_code == 200
        assert reloaded.json() == updated.json()

        with postgres_engine.connect() as connection:
            stored = connection.execute(
                select(user_preferences.c.value_of_time_per_hour).where(
                    user_preferences.c.user_id == user_id.value
                )
            ).scalar_one()

        assert stored == Decimal("33.123456789")

    finally:
        with postgres_engine.begin() as connection:
            connection.execute(delete(users).where(users.c.id == user_id.value))
