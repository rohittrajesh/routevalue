"""Tests for FastAPI's provider-neutral authentication boundary."""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from routevalue.api.authentication import (
    get_authentication_verifier,
    get_verified_external_identity,
)
from routevalue.api.errors import (
    AuthenticationRequiredError,
    AuthenticationServiceUnavailableError,
    ServiceConfigurationError,
    authentication_required_error_handler,
    authentication_service_unavailable_error_handler,
    service_configuration_error_handler,
)
from routevalue.application.identity import (
    AuthenticationVerificationUnavailableError,
    InvalidAuthenticationError,
    VerifiedExternalIdentity,
)
from routevalue.application.ports import AuthenticationVerifier


class AcceptingVerifier:
    """Return one deterministic verified identity."""

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
    """Reject every token as invalid."""

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        del token
        raise InvalidAuthenticationError


class UnavailableVerifier:
    """Simulate temporary JWKS/provider unavailability."""

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        del token
        raise AuthenticationVerificationUnavailableError


def _test_app(
    verifier: AuthenticationVerifier,
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

    @app.get("/protected")
    def protected_route(
        identity: Annotated[
            VerifiedExternalIdentity,
            Depends(get_verified_external_identity),
        ],
    ) -> dict[str, str]:
        return {
            "issuer": identity.issuer,
            "subject": identity.subject,
        }

    return app


def test_valid_bearer_token_returns_verified_identity() -> None:
    client = TestClient(_test_app(AcceptingVerifier()))

    response = client.get(
        "/protected",
        headers={
            "Authorization": "Bearer valid-token",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "issuer": "https://auth.example.test",
        "subject": "external-user-123",
    }


def test_missing_authorization_header_returns_401() -> None:
    client = TestClient(_test_app(AcceptingVerifier()))

    response = client.get("/protected")

    assert response.status_code == 401
    assert response.json() == {
        "code": "authentication_required",
        "detail": "Authentication is required.",
    }
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "authorization",
    [
        "Basic abc123",
        "Digest abc123",
    ],
)
def test_non_bearer_authorization_returns_401(
    authorization: str,
) -> None:
    client = TestClient(_test_app(AcceptingVerifier()))

    response = client.get(
        "/protected",
        headers={
            "Authorization": authorization,
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_invalid_bearer_token_returns_401() -> None:
    client = TestClient(_test_app(RejectingVerifier()))

    response = client.get(
        "/protected",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "authentication_required",
        "detail": "Authentication is required.",
    }


def test_authentication_provider_failure_returns_503() -> None:
    client = TestClient(_test_app(UnavailableVerifier()))

    response = client.get(
        "/protected",
        headers={
            "Authorization": "Bearer valid-looking-token",
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "authentication_service_unavailable",
        "detail": ("Authentication is temporarily unavailable. Please try again."),
    }


def test_invalid_token_is_not_exposed_in_response() -> None:
    client = TestClient(_test_app(RejectingVerifier()))

    secret_token = "sensitive-invalid-token"

    response = client.get(
        "/protected",
        headers={
            "Authorization": f"Bearer {secret_token}",
        },
    )

    assert secret_token not in response.text


def test_provider_error_details_are_not_exposed() -> None:
    client = TestClient(_test_app(UnavailableVerifier()))

    response = client.get(
        "/protected",
        headers={
            "Authorization": "Bearer token",
        },
    )

    assert "JWKS" not in response.text
    assert "signing" not in response.text.lower()
