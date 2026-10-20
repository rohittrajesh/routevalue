"""End-to-end authenticated PostgreSQL integration for V2 preferences."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Engine

from routevalue.api.authentication import (
    get_authentication_verifier,
)
from routevalue.api.preferences import (
    get_user_preferences_repository,
)
from routevalue.api.saved_vehicles import (
    get_saved_vehicle_repository,
)
from routevalue.api.user_identity import (
    get_user_identity_repository,
)
from routevalue.application.identity import (
    VerifiedExternalIdentity,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    PostgresSavedVehicleRepository,
)
from routevalue.infrastructure.persistence.schema import (
    auth_identities,
    saved_vehicles,
    user_preferences,
    users,
)
from routevalue.infrastructure.persistence.user_identity import (
    PostgresUserIdentityRepository,
)
from routevalue.infrastructure.persistence.user_preferences import (
    PostgresUserPreferencesRepository,
)
from routevalue.main import create_app


class AcceptingVerifier:
    """Return one deterministic verified external identity."""

    def __init__(
        self,
        identity: VerifiedExternalIdentity,
    ) -> None:
        self._identity = identity

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        assert token == "valid-token"

        return self._identity


def _create_saved_vehicle(
    engine: Engine,
    *,
    user_id: UUID,
) -> UUID:
    vehicle_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            insert(saved_vehicles).values(
                id=vehicle_id,
                user_id=user_id,
                year=2025,
                make="Honda",
                model="Civic",
                configuration=("Authenticated test configuration"),
                source="fueleconomy.gov",
                source_id=(f"auth-test-{uuid4().hex}"),
                specification_retrieved_at=(datetime.now(UTC)),
                powertrain="gasoline",
                gasoline_grade="regular",
                combined_mpg=Decimal("36.5"),
                city_mpg=Decimal("33.0"),
                highway_mpg=Decimal("41.0"),
            )
        )

    return vehicle_id


def test_authenticated_profile_and_preferences_flow_persists_for_resolved_user(
    postgres_engine: Engine,
) -> None:
    identity = VerifiedExternalIdentity(
        issuer=(f"https://auth-{uuid4().hex}.example.test"),
        subject=(f"subject-{uuid4().hex}"),
    )

    identity_repository = PostgresUserIdentityRepository(
        engine=postgres_engine,
    )

    preferences_repository = PostgresUserPreferencesRepository(
        engine=postgres_engine,
    )

    vehicle_repository = PostgresSavedVehicleRepository(
        engine=postgres_engine,
    )

    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: AcceptingVerifier(identity)

    app.dependency_overrides[get_user_identity_repository] = lambda: identity_repository

    app.dependency_overrides[get_user_preferences_repository] = lambda: preferences_repository

    app.dependency_overrides[get_saved_vehicle_repository] = lambda: vehicle_repository

    try:
        with TestClient(app) as client:
            initial = client.get(
                "/api/v2/preferences",
                headers={
                    "Authorization": ("Bearer valid-token"),
                },
            )

            assert initial.status_code == 200

            assert initial.json() == {
                "value_of_time_per_hour": None,
                "default_vehicle_id": None,
                "electricity_price_per_kwh": None,
                "preferred_fuel_market": None,
            }

            with postgres_engine.connect() as connection:
                user_id = connection.execute(
                    select(auth_identities.c.user_id).where(
                        auth_identities.c.issuer == identity.issuer,
                        auth_identities.c.subject == identity.subject,
                    )
                ).scalar_one()

            vehicle_id = _create_saved_vehicle(
                postgres_engine,
                user_id=user_id,
            )

            updated = client.patch(
                "/api/v2/preferences",
                headers={
                    "Authorization": ("Bearer valid-token"),
                },
                json={
                    "value_of_time_per_hour": ("41.375"),
                    "default_vehicle_id": (str(vehicle_id)),
                },
            )

            assert updated.status_code == 200

            assert updated.json() == {
                "value_of_time_per_hour": ("41.375"),
                "default_vehicle_id": (str(vehicle_id)),
                "electricity_price_per_kwh": None,
                "preferred_fuel_market": None,
            }

            reloaded = client.get(
                "/api/v2/preferences",
                headers={
                    "Authorization": ("Bearer valid-token"),
                },
            )

            assert reloaded.status_code == 200
            assert reloaded.json() == updated.json()

            profile = client.get(
                "/api/v2/me",
                headers={
                    "Authorization": ("Bearer valid-token"),
                },
            )

            assert profile.status_code == 200

            assert profile.json() == {
                "user_id": str(user_id),
                "preferences_configured": True,
                "default_vehicle_id": (str(vehicle_id)),
            }

        with postgres_engine.connect() as connection:
            stored = (
                connection.execute(
                    select(
                        user_preferences.c.value_of_time_per_hour,
                        user_preferences.c.default_vehicle_id,
                    ).where(user_preferences.c.user_id == user_id)
                )
                .mappings()
                .one()
            )

        assert stored["value_of_time_per_hour"] == Decimal("41.375")

        assert stored["default_vehicle_id"] == vehicle_id

    finally:
        with postgres_engine.begin() as connection:
            user_id = connection.execute(
                select(auth_identities.c.user_id).where(
                    auth_identities.c.issuer == identity.issuer,
                    auth_identities.c.subject == identity.subject,
                )
            ).scalar_one_or_none()

            if user_id is not None:
                connection.execute(delete(users).where(users.c.id == user_id))
