"""Tests for the authenticated RouteValue profile resource."""

from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routevalue.api.preferences import (
    get_user_preferences_repository,
)
from routevalue.api.profile import (
    router,
)
from routevalue.api.user_identity import (
    get_authenticated_user,
)
from routevalue.application.identity import (
    AuthenticatedUser,
)
from routevalue.application.preferences import (
    UserPreferences,
)
from routevalue.domain.identity import (
    SavedVehicleId,
    UserId,
)


class FakePreferencesRepository:
    """Return deterministic persisted preferences for profile tests."""

    def __init__(
        self,
        preferences: UserPreferences,
    ) -> None:
        self._preferences = preferences

    def get_preferences(
        self,
        user_id: UserId,
    ) -> UserPreferences:
        del user_id

        return self._preferences

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        del user_id

        self._preferences = preferences

        return preferences


def _client(
    *,
    user_id: UserId,
    preferences: UserPreferences,
) -> TestClient:
    app = FastAPI()

    app.include_router(router)

    repository = FakePreferencesRepository(preferences)

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)

    app.dependency_overrides[get_user_preferences_repository] = lambda: repository

    return TestClient(app)


def test_profile_returns_internal_routevalue_user() -> None:
    user_id = UserId(value=uuid4())

    response = _client(
        user_id=user_id,
        preferences=UserPreferences(),
    ).get("/api/v2/me")

    assert response.status_code == 200

    assert response.json() == {
        "user_id": str(user_id.value),
        "preferences_configured": False,
        "default_vehicle_id": None,
    }


def test_profile_reports_configured_value_of_time() -> None:
    user_id = UserId(value=uuid4())

    response = _client(
        user_id=user_id,
        preferences=UserPreferences(value_of_time_per_hour=(Decimal(30))),
    ).get("/api/v2/me")

    assert response.status_code == 200

    assert response.json()["preferences_configured"] is True


def test_profile_reports_default_vehicle() -> None:
    user_id = UserId(value=uuid4())

    vehicle_id = SavedVehicleId(value=uuid4())

    response = _client(
        user_id=user_id,
        preferences=UserPreferences(
            default_vehicle_id=vehicle_id,
        ),
    ).get("/api/v2/me")

    assert response.status_code == 200

    assert response.json() == {
        "user_id": str(user_id.value),
        "preferences_configured": True,
        "default_vehicle_id": str(vehicle_id.value),
    }
