"""Tests for cached API infrastructure resource cleanup."""

import pytest
from fastapi.testclient import TestClient

from routevalue.api.user_identity import (
    close_user_identity_resources,
    get_application_database_engine,
    get_user_identity_repository,
)
from routevalue.main import create_app


def test_identity_resources_can_be_explicitly_disposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        ("postgresql+psycopg://routevalue:placeholder@localhost/routevalue"),
    )

    close_user_identity_resources()

    engine = get_application_database_engine()
    repository = get_user_identity_repository()

    old_pool = engine.pool

    close_user_identity_resources()

    assert get_application_database_engine.cache_info().currsize == 0

    assert get_user_identity_repository.cache_info().currsize == 0

    assert engine.pool is not old_pool

    replacement = get_user_identity_repository()

    try:
        assert replacement is not repository

    finally:
        close_user_identity_resources()


def test_fastapi_shutdown_clears_identity_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        ("postgresql+psycopg://routevalue:placeholder@localhost/routevalue"),
    )

    close_user_identity_resources()

    _ = get_user_identity_repository()

    assert get_user_identity_repository.cache_info().currsize == 1

    with TestClient(create_app()) as client:
        response = client.get("/health")

        assert response.status_code == 200

    assert get_user_identity_repository.cache_info().currsize == 0

    assert get_application_database_engine.cache_info().currsize == 0


def test_fastapi_shutdown_clears_preferences_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from routevalue.api.preferences import (
        get_user_preferences_repository,
    )

    monkeypatch.setenv(
        "DATABASE_URL",
        ("postgresql+psycopg://routevalue:placeholder@localhost/routevalue"),
    )

    close_user_identity_resources()
    get_user_preferences_repository.cache_clear()

    _ = get_user_preferences_repository()

    assert get_user_preferences_repository.cache_info().currsize == 1

    with TestClient(create_app()) as client:
        response = client.get("/health")

        assert response.status_code == 200

    assert get_user_preferences_repository.cache_info().currsize == 0

    assert get_application_database_engine.cache_info().currsize == 0


def test_fastapi_shutdown_clears_saved_vehicle_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from routevalue.api.saved_vehicles import (
        close_saved_vehicle_resources,
        get_saved_vehicle_repository,
        get_vehicle_http_client,
        get_vehicle_specification_provider,
    )

    monkeypatch.setenv(
        "DATABASE_URL",
        ("postgresql+psycopg://routevalue:placeholder@localhost/routevalue"),
    )

    close_saved_vehicle_resources()
    close_user_identity_resources()

    _ = get_saved_vehicle_repository()
    client = get_vehicle_http_client()
    _ = get_vehicle_specification_provider()

    assert get_saved_vehicle_repository.cache_info().currsize == 1

    assert get_vehicle_http_client.cache_info().currsize == 1

    assert get_vehicle_specification_provider.cache_info().currsize == 1

    with TestClient(create_app()) as test_client:
        response = test_client.get("/health")

        assert response.status_code == 200

    assert client.is_closed

    assert get_saved_vehicle_repository.cache_info().currsize == 0

    assert get_vehicle_http_client.cache_info().currsize == 0

    assert get_vehicle_specification_provider.cache_info().currsize == 0

    assert get_application_database_engine.cache_info().currsize == 0
