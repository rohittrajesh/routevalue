"""End-to-end authenticated PostgreSQL integration for V2 preferences."""

from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine

from routevalue.api.authentication import (
    get_authentication_verifier,
)
from routevalue.api.preferences import (
    get_user_preferences_repository,
)
from routevalue.api.user_identity import (
    get_user_identity_repository,
)
from routevalue.application.identity import (
    VerifiedExternalIdentity,
)
from routevalue.infrastructure.persistence.schema import (
    auth_identities,
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


def test_authenticated_preferences_flow_persists_for_resolved_user(
    postgres_engine: Engine,
) -> None:
    identity = VerifiedExternalIdentity(
        issuer=f"https://auth-{uuid4().hex}.example.test",
        subject=f"subject-{uuid4().hex}",
    )

    identity_repository = PostgresUserIdentityRepository(
        engine=postgres_engine,
    )

    preferences_repository = PostgresUserPreferencesRepository(
        engine=postgres_engine,
    )

    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: AcceptingVerifier(identity)

    app.dependency_overrides[get_user_identity_repository] = lambda: identity_repository

    app.dependency_overrides[get_user_preferences_repository] = lambda: preferences_repository

    try:
        with TestClient(app) as client:
            initial = client.get(
                "/api/v2/preferences",
                headers={
                    "Authorization": "Bearer valid-token",
                },
            )

            assert initial.status_code == 200
            assert initial.json() == {
                "value_of_time_per_hour": None,
            }

            updated = client.patch(
                "/api/v2/preferences",
                headers={
                    "Authorization": "Bearer valid-token",
                },
                json={
                    "value_of_time_per_hour": "41.375",
                },
            )

            assert updated.status_code == 200
            assert updated.json() == {
                "value_of_time_per_hour": "41.375",
            }

            reloaded = client.get(
                "/api/v2/preferences",
                headers={
                    "Authorization": "Bearer valid-token",
                },
            )

            assert reloaded.status_code == 200
            assert reloaded.json() == updated.json()

        with postgres_engine.connect() as connection:
            user_id = connection.execute(
                select(auth_identities.c.user_id).where(
                    auth_identities.c.issuer == identity.issuer,
                    auth_identities.c.subject == identity.subject,
                )
            ).scalar_one()

            stored_value = connection.execute(
                select(user_preferences.c.value_of_time_per_hour).where(
                    user_preferences.c.user_id == user_id
                )
            ).scalar_one()

        assert stored_value == Decimal("41.375")

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
