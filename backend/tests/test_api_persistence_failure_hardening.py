"""Persistence-failure hardening for authenticated RouteValue V2 APIs."""

from collections.abc import Sequence
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import Response

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
    get_authenticated_user,
    get_user_identity_repository,
)
from routevalue.application.identity import (
    AuthenticatedUser,
    VerifiedExternalIdentity,
)
from routevalue.application.preferences import UserPreferences
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleSnapshot,
)
from routevalue.domain.identity import (
    SavedVehicleId,
    UserId,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    SavedVehiclePersistenceError,
)
from routevalue.infrastructure.persistence.user_identity import (
    UserIdentityPersistenceError,
)
from routevalue.infrastructure.persistence.user_preferences import (
    UserPreferencesPersistenceError,
)
from routevalue.main import create_app

_SENSITIVE_DATABASE_DETAIL = (
    "postgresql+psycopg://routevalue:super-secret-password@private-db.example.test/routevalue"
)


class AcceptingVerifier:
    """Return one deterministic verified identity."""

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


class FailingIdentityRepository:
    """Simulate a persistence failure during identity resolution."""

    def get_or_create_user_id(
        self,
        identity: VerifiedExternalIdentity,
    ) -> UserId:
        del identity

        raise UserIdentityPersistenceError(_SENSITIVE_DATABASE_DETAIL)


class FailingPreferencesRepository:
    """Simulate failures in persisted preference access."""

    def get_preferences(
        self,
        user_id: UserId,
    ) -> UserPreferences:
        del user_id

        raise UserPreferencesPersistenceError(_SENSITIVE_DATABASE_DETAIL)

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        del user_id
        del preferences

        raise UserPreferencesPersistenceError(_SENSITIVE_DATABASE_DETAIL)


class FailingSavedVehicleRepository:
    """Simulate failures in persisted saved-vehicle access."""

    def list_vehicles(
        self,
        user_id: UserId,
    ) -> Sequence[SavedVehicle]:
        del user_id

        raise SavedVehiclePersistenceError(_SENSITIVE_DATABASE_DETAIL)

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        del user_id
        del vehicle_id

        raise SavedVehiclePersistenceError(_SENSITIVE_DATABASE_DETAIL)

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        del user_id
        del snapshot

        raise SavedVehiclePersistenceError(_SENSITIVE_DATABASE_DETAIL)

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        del user_id
        del vehicle_id

        raise SavedVehiclePersistenceError(_SENSITIVE_DATABASE_DETAIL)


def _authenticated_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=UserId(value=uuid4()),
    )


def _assert_safe_internal_failure(
    response: Response,
) -> None:
    """Require a generic failure without leaking infrastructure details."""

    assert response.status_code == 500

    assert "super-secret-password" not in response.text
    assert "private-db.example.test" not in response.text
    assert "postgresql+psycopg" not in response.text


def test_identity_persistence_failure_does_not_leak_database_details() -> None:
    identity = VerifiedExternalIdentity(
        issuer="https://auth.example.test",
        subject=f"subject-{uuid4().hex}",
    )

    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: AcceptingVerifier(identity)

    app.dependency_overrides[get_user_identity_repository] = lambda: FailingIdentityRepository()

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/api/v2/preferences",
            headers={
                "Authorization": "Bearer valid-token",
            },
        )

    _assert_safe_internal_failure(response)


def test_preferences_persistence_failure_does_not_leak_database_details() -> None:
    app = create_app()

    app.dependency_overrides[get_authenticated_user] = _authenticated_user

    app.dependency_overrides[get_user_preferences_repository] = lambda: (
        FailingPreferencesRepository()
    )

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/api/v2/preferences",
        )

    _assert_safe_internal_failure(response)


def test_saved_vehicle_persistence_failure_does_not_leak_database_details() -> None:
    app = create_app()

    app.dependency_overrides[get_authenticated_user] = _authenticated_user

    app.dependency_overrides[get_saved_vehicle_repository] = lambda: FailingSavedVehicleRepository()

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/api/v2/vehicles",
        )

    _assert_safe_internal_failure(response)
