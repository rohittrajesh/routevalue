"""Real JWT verification, HTTP and PostgreSQL identity/session acceptance.

Keys are ephemeral test keys; JWKS is local. No Neon credentials or accounts are used.
"""

from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from test_neon_jwt import StaticJwksClient, _settings, _token

from routevalue.api.authentication import get_authentication_verifier
from routevalue.api.preferences import get_user_preferences_repository
from routevalue.api.saved_vehicles import get_saved_vehicle_repository
from routevalue.api.user_identity import get_user_identity_repository
from routevalue.infrastructure.auth.neon_jwt import NeonJWTAuthenticationVerifier
from routevalue.infrastructure.persistence.saved_vehicles import PostgresSavedVehicleRepository
from routevalue.infrastructure.persistence.schema import auth_identities, users
from routevalue.infrastructure.persistence.user_identity import PostgresUserIdentityRepository
from routevalue.infrastructure.persistence.user_preferences import PostgresUserPreferencesRepository
from routevalue.main import create_app


def test_new_signed_session_restores_identity_but_expired_session_cannot_write(
    postgres_engine: Engine,
) -> None:
    key = Ed25519PrivateKey.generate()
    subject, other_subject = f"session-{uuid4()}", f"session-{uuid4()}"
    verifier = NeonJWTAuthenticationVerifier(
        settings=_settings(), jwks_client=StaticJwksClient(key)
    )
    app = create_app()
    app.dependency_overrides[get_authentication_verifier] = lambda: verifier
    app.dependency_overrides[get_user_identity_repository] = lambda: PostgresUserIdentityRepository(
        engine=postgres_engine
    )
    app.dependency_overrides[get_user_preferences_repository] = lambda: (
        PostgresUserPreferencesRepository(engine=postgres_engine)
    )
    app.dependency_overrides[get_saved_vehicle_repository] = lambda: PostgresSavedVehicleRepository(
        engine=postgres_engine
    )
    tracked: list[UUID] = []
    try:
        with TestClient(app) as client:

            def headers(**claims: object) -> dict[str, str]:
                return {"Authorization": f"Bearer {_token(key, sub=subject, **claims)}"}

            first = client.get("/api/v2/me", headers=headers(jti="first-session"))
            assert first.status_code == 200
            user_id = UUID(first.json()["user_id"])
            tracked.append(user_id)
            preferences = {"value_of_time_per_hour": "24.125", "electricity_price_per_kwh": "0.275"}
            saved = client.patch("/api/v2/preferences", json=preferences, headers=headers())
            assert saved.status_code == 200

            expired = client.patch(
                "/api/v2/preferences",
                json={"electricity_price_per_kwh": "9"},
                headers=headers(exp=1),
            )
            assert expired.status_code == 401
            assert expired.json()["code"] == "authentication_required"
            assert expired.headers["www-authenticate"] == "Bearer"
            assert client.get("/api/v2/preferences").status_code == 401

            # A newly issued JWT for the same verified subject reuses the mapping.
            returned = client.get("/api/v2/me", headers=headers(jti="new-session"))
            assert returned.status_code == 200
            assert returned.json()["user_id"] == str(user_id)
            restored = client.get("/api/v2/preferences", headers=headers(jti="new-session"))
            assert restored.json() == saved.json()

            other_headers = {"Authorization": f"Bearer {_token(key, sub=other_subject)}"}
            other = client.get("/api/v2/me", headers=other_headers)
            assert other.status_code == 200
            tracked.append(UUID(other.json()["user_id"]))
            assert tracked[-1] != user_id
            assert (
                client.get("/api/v2/preferences", headers=other_headers).json()[
                    "electricity_price_per_kwh"
                ]
                is None
            )

            # Invalid first-time credentials must not create a permanent user mapping.
            invalid_subject = f"expired-{uuid4()}"
            rejected = client.get(
                "/api/v2/me",
                headers={"Authorization": f"Bearer {_token(key, sub=invalid_subject, exp=1)}"},
            )
            assert rejected.status_code == 401
            with postgres_engine.connect() as connection:
                assert (
                    connection.execute(
                        select(auth_identities.c.id).where(
                            auth_identities.c.subject == invalid_subject
                        )
                    ).first()
                    is None
                )
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(delete(users).where(users.c.id.in_(tracked)))
