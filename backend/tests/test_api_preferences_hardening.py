"""Security and contract hardening for authenticated V2 preferences."""

from typing import Any

from fastapi.testclient import TestClient

from routevalue.main import create_app


def _bearer_security_scheme_names(
    schema: dict[str, Any],
) -> set[str]:
    schemes = schema["components"]["securitySchemes"]

    return {
        name
        for name, definition in schemes.items()
        if definition.get("type") == "http" and definition.get("scheme") == "bearer"
    }


def test_preferences_endpoints_require_bearer_authentication_in_openapi() -> None:
    schema: dict[str, Any] = create_app().openapi()

    bearer_schemes = _bearer_security_scheme_names(schema)

    assert bearer_schemes

    for method in (
        "get",
        "patch",
    ):
        operation = schema["paths"]["/api/v2/preferences"][method]

        configured_schemes = {name for requirement in operation["security"] for name in requirement}

        assert configured_schemes & bearer_schemes


def test_preferences_patch_contract_contains_no_user_id() -> None:
    schema: dict[str, Any] = create_app().openapi()

    request_schema = schema["components"]["schemas"]["UserPreferencesUpdateRequest"]

    assert set(request_schema["properties"]) == {
        "value_of_time_per_hour",
    }

    assert "value_of_time_per_hour" in request_schema["required"]


def test_preferences_endpoint_without_bearer_returns_401() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v2/preferences")

    assert response.status_code == 401

    assert response.json() == {
        "code": "authentication_required",
        "detail": "Authentication is required.",
    }

    assert response.headers["www-authenticate"] == "Bearer"
