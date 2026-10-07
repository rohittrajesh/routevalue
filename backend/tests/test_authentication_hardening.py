"""Hardening checks for RouteValue's authentication boundary."""

from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from routevalue.api.authentication import (
    get_authentication_verifier,
    get_verified_external_identity,
)
from routevalue.api.errors import (
    ServiceConfigurationError,
    service_configuration_error_handler,
)
from routevalue.application.identity import VerifiedExternalIdentity
from routevalue.main import create_app


def test_authentication_verifier_is_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "NEON_AUTH_BASE_URL",
        "https://branch.neonauth.example.test/neondb/auth",
    )
    monkeypatch.setenv(
        "NEON_AUTH_JWKS_URL",
        "https://branch.neonauth.example.test/neondb/auth/jwks",
    )
    monkeypatch.delenv(
        "ROUTEVALUE_AUTH_AUDIENCE",
        raising=False,
    )

    get_authentication_verifier.cache_clear()

    try:
        first = get_authentication_verifier()
        second = get_authentication_verifier()

        assert first is second

    finally:
        get_authentication_verifier.cache_clear()


def test_missing_authentication_configuration_returns_safe_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "NEON_AUTH_BASE_URL",
        raising=False,
    )
    monkeypatch.delenv(
        "NEON_AUTH_JWKS_URL",
        raising=False,
    )
    monkeypatch.delenv(
        "ROUTEVALUE_AUTH_AUDIENCE",
        raising=False,
    )

    get_authentication_verifier.cache_clear()

    app = FastAPI()

    app.add_exception_handler(
        ServiceConfigurationError,
        service_configuration_error_handler,
    )

    @app.get("/protected")
    def protected(
        identity: Annotated[
            VerifiedExternalIdentity,
            Depends(get_verified_external_identity),
        ],
    ) -> dict[str, str]:
        return {
            "subject": identity.subject,
        }

    try:
        response = TestClient(app).get(
            "/protected",
            headers={
                "Authorization": "Bearer token",
            },
        )

    finally:
        get_authentication_verifier.cache_clear()

    assert response.status_code == 500
    assert response.json() == {
        "code": "service_configuration_error",
        "detail": ("RouteValue is temporarily unavailable. Please try again later."),
    }

    assert "NEON_AUTH" not in response.text
    assert "JWKS" not in response.text


def test_v1_trip_evaluation_openapi_remains_unauthenticated() -> None:
    schema: dict[str, Any] = create_app().openapi()

    operation = schema["paths"]["/trip-evaluations"]["post"]

    assert "security" not in operation or operation["security"] == []
