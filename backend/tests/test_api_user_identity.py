"""Tests for FastAPI internal RouteValue user resolution."""

from typing import Annotated
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from routevalue.api.authentication import (
    get_authentication_verifier,
)
from routevalue.api.errors import (
    AuthenticationRequiredError,
    AuthenticationServiceUnavailableError,
    ServiceConfigurationError,
    authentication_required_error_handler,
    authentication_service_unavailable_error_handler,
    service_configuration_error_handler,
)
from routevalue.api.user_identity import (
    get_authenticated_user,
    get_authenticated_user_resolver,
    get_user_identity_repository,
)
from routevalue.application.identity import (
    AuthenticatedUser,
    InvalidAuthenticationError,
    VerifiedExternalIdentity,
)
from routevalue.application.ports import (
    AuthenticationVerifier,
    UserIdentityRepository,
)
from routevalue.application.user_identity import (
    AuthenticatedUserResolver,
)
from routevalue.domain.identity import UserId


class AcceptingVerifier:
    """Accept one deterministic bearer token."""

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        assert token == "valid-token"

        return VerifiedExternalIdentity(
            issuer="https://auth.example.test",
            subject="external-user-123",
        )


class RejectingVerifier:
    """Reject every bearer token."""

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        del token
        raise InvalidAuthenticationError


class RecordingRepository:
    """Return one stable internal user while recording requests."""

    def __init__(
        self,
        user_id: UserId,
    ) -> None:
        self._user_id = user_id
        self.requests: list[VerifiedExternalIdentity] = []

    def get_or_create_user_id(
        self,
        identity: VerifiedExternalIdentity,
    ) -> UserId:
        self.requests.append(identity)

        return self._user_id


def _test_app(
    verifier: AuthenticationVerifier,
    repository: UserIdentityRepository,
) -> FastAPI:
    app = FastAPI()

    app.add_exception_handler(
        AuthenticationRequiredError,
        authentication_required_error_handler,
    )
    app.add_exception_handler(
        AuthenticationServiceUnavailableError,
        authentication_service_unavailable_error_handler,
    )
    app.add_exception_handler(
        ServiceConfigurationError,
        service_configuration_error_handler,
    )

    app.dependency_overrides[get_authentication_verifier] = lambda: verifier

    app.dependency_overrides[get_user_identity_repository] = lambda: repository

    @app.get("/protected-user")
    def protected_user(
        user: Annotated[
            AuthenticatedUser,
            Depends(get_authenticated_user),
        ],
    ) -> dict[str, str]:
        return {
            "user_id": str(user.user_id.value),
        }

    return app


def test_valid_bearer_resolves_internal_routevalue_user() -> None:
    user_id = UserId(value=uuid4())

    repository = RecordingRepository(user_id)

    client = TestClient(
        _test_app(
            AcceptingVerifier(),
            repository,
        )
    )

    response = client.get(
        "/protected-user",
        headers={
            "Authorization": "Bearer valid-token",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user_id.value),
    }


def test_repository_receives_verified_external_identity() -> None:
    repository = RecordingRepository(UserId(value=uuid4()))

    client = TestClient(
        _test_app(
            AcceptingVerifier(),
            repository,
        )
    )

    response = client.get(
        "/protected-user",
        headers={
            "Authorization": "Bearer valid-token",
        },
    )

    assert response.status_code == 200

    assert repository.requests == [
        VerifiedExternalIdentity(
            issuer="https://auth.example.test",
            subject="external-user-123",
        )
    ]


def test_missing_bearer_does_not_resolve_user() -> None:
    repository = RecordingRepository(UserId(value=uuid4()))

    client = TestClient(
        _test_app(
            AcceptingVerifier(),
            repository,
        )
    )

    response = client.get("/protected-user")

    assert response.status_code == 401
    assert repository.requests == []


def test_invalid_bearer_does_not_resolve_user() -> None:
    repository = RecordingRepository(UserId(value=uuid4()))

    client = TestClient(
        _test_app(
            RejectingVerifier(),
            repository,
        )
    )

    response = client.get(
        "/protected-user",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert repository.requests == []


def test_internal_user_id_is_uuid_not_external_subject() -> None:
    user_id = UserId(value=uuid4())

    repository = RecordingRepository(user_id)

    client = TestClient(
        _test_app(
            AcceptingVerifier(),
            repository,
        )
    )

    response = client.get(
        "/protected-user",
        headers={
            "Authorization": "Bearer valid-token",
        },
    )

    returned_user_id = UUID(response.json()["user_id"])

    assert returned_user_id == user_id.value
    assert str(returned_user_id) != "external-user-123"


def test_missing_database_configuration_returns_safe_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "DATABASE_URL",
        raising=False,
    )

    get_user_identity_repository.cache_clear()

    app = FastAPI()

    app.add_exception_handler(
        ServiceConfigurationError,
        service_configuration_error_handler,
    )

    try:
        response = TestClient(
            app,
            raise_server_exceptions=False,
        )

        @app.get("/database-user")
        def database_user(
            resolver: Annotated[
                AuthenticatedUserResolver,
                Depends(get_authenticated_user_resolver),
            ],
        ) -> dict[str, bool]:
            del resolver

            return {
                "configured": True,
            }

        result = response.get("/database-user")

    finally:
        get_user_identity_repository.cache_clear()

    assert result.status_code == 500
    assert result.json() == {
        "code": "service_configuration_error",
        "detail": ("RouteValue is temporarily unavailable. Please try again later."),
    }

    assert "DATABASE_URL" not in result.text


def test_production_identity_repository_is_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        ("postgresql+psycopg://routevalue:placeholder@localhost/routevalue"),
    )

    get_user_identity_repository.cache_clear()

    try:
        first = get_user_identity_repository()
        second = get_user_identity_repository()

        assert first is second

    finally:
        get_user_identity_repository.cache_clear()
