import pytest
from fastapi.testclient import TestClient

from routevalue.main import app, create_app


def test_health_check_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_is_disabled_when_no_origins_are_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ROUTEVALUE_CORS_ORIGINS", raising=False)

    client = TestClient(create_app())

    response = client.options(
        "/trip-evaluations",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 405
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_configured_frontend_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frontend_origin = "https://routevalue.example.com"

    monkeypatch.setenv(
        "ROUTEVALUE_CORS_ORIGINS",
        frontend_origin,
    )

    client = TestClient(create_app())

    response = client.options(
        "/trip-evaluations",
        headers={
            "Origin": frontend_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == frontend_origin


def test_cors_rejects_unconfigured_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ROUTEVALUE_CORS_ORIGINS",
        "https://routevalue.example.com",
    )

    client = TestClient(create_app())

    response = client.options(
        "/trip-evaluations",
        headers={
            "Origin": "https://not-routevalue.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
