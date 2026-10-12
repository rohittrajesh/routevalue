"""Cross-cutting authorization hardening for RouteValue V2 APIs."""

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from routevalue.api.authentication import (
    get_authentication_verifier,
)
from routevalue.application.identity import (
    AuthenticationVerificationUnavailableError,
    InvalidAuthenticationError,
    VerifiedExternalIdentity,
)
from routevalue.main import create_app


class RejectingVerifier:
    """Reject every bearer credential as invalid or expired."""

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        raise InvalidAuthenticationError(f"rejected sensitive credential: {token}")


class UnavailableVerifier:
    """Simulate temporary authentication-provider failure."""

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        del token

        raise AuthenticationVerificationUnavailableError("JWKS signing-key service is unavailable")


_PROTECTED_REQUESTS: tuple[
    tuple[
        str,
        str,
        Mapping[str, Any] | None,
    ],
    ...,
] = (
    (
        "GET",
        "/api/v2/me",
        None,
    ),
    (
        "GET",
        "/api/v2/preferences",
        None,
    ),
    (
        "PATCH",
        "/api/v2/preferences",
        {},
    ),
    (
        "GET",
        "/api/v2/vehicles",
        None,
    ),
    (
        "POST",
        "/api/v2/vehicles",
        {
            "year": 2025,
            "make": "Toyota",
            "model": "Camry",
            "configuration": "2.5L 4cyl CVT (FWD)",
            "source": "fueleconomy_gov",
            "source_id": "12345",
        },
    ),
    (
        "GET",
        f"/api/v2/vehicles/{uuid4()}",
        None,
    ),
    (
        "DELETE",
        f"/api/v2/vehicles/{uuid4()}",
        None,
    ),
)


@pytest.mark.parametrize(
    (
        "method",
        "path",
        "json_body",
    ),
    _PROTECTED_REQUESTS,
)
def test_invalid_or_expired_bearer_is_uniformly_rejected(
    method: str,
    path: str,
    json_body: Mapping[str, Any] | None,
) -> None:
    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: RejectingVerifier()

    secret_token = "sensitive-expired-token"

    with TestClient(app) as client:
        response = client.request(
            method,
            path,
            headers={
                "Authorization": (f"Bearer {secret_token}"),
            },
            json=json_body,
        )

    assert response.status_code == 401

    assert response.json() == {
        "code": "authentication_required",
        "detail": "Authentication is required.",
    }

    assert response.headers["www-authenticate"] == "Bearer"

    assert secret_token not in response.text
    assert "rejected sensitive credential" not in response.text


@pytest.mark.parametrize(
    (
        "method",
        "path",
        "json_body",
    ),
    _PROTECTED_REQUESTS,
)
def test_authentication_provider_failure_is_uniformly_safe(
    method: str,
    path: str,
    json_body: Mapping[str, Any] | None,
) -> None:
    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: UnavailableVerifier()

    with TestClient(app) as client:
        response = client.request(
            method,
            path,
            headers={
                "Authorization": ("Bearer valid-looking-token"),
            },
            json=json_body,
        )

    assert response.status_code == 503

    assert response.json() == {
        "code": ("authentication_service_unavailable"),
        "detail": ("Authentication is temporarily unavailable. Please try again."),
    }

    assert "JWKS" not in response.text
    assert "signing-key" not in response.text
