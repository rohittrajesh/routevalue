"""Tests for authenticated V2 preference resources."""

from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routevalue.api.preferences import (
    get_user_preferences_repository,
    router,
)
from routevalue.api.user_identity import (
    get_authenticated_user,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.preferences import UserPreferences
from routevalue.domain.identity import UserId


class RecordingPreferencesRepository:
    """In-memory repository that records internal-user ownership."""

    def __init__(self) -> None:
        self.preferences: dict[
            UserId,
            UserPreferences,
        ] = {}

        self.get_requests: list[UserId] = []

        self.save_requests: list[tuple[UserId, UserPreferences]] = []

    def get_preferences(
        self,
        user_id: UserId,
    ) -> UserPreferences:
        self.get_requests.append(user_id)

        return self.preferences.get(
            user_id,
            UserPreferences(),
        )

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        self.save_requests.append(
            (
                user_id,
                preferences,
            )
        )

        self.preferences[user_id] = preferences

        return preferences


def _test_client(
    *,
    user_id: UserId,
    repository: RecordingPreferencesRepository,
) -> TestClient:
    app = FastAPI()

    app.include_router(router)

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)

    app.dependency_overrides[get_user_preferences_repository] = lambda: repository

    return TestClient(app)


def test_get_preferences_returns_unset_state_for_new_user() -> None:
    user_id = UserId(value=uuid4())

    repository = RecordingPreferencesRepository()

    response = _test_client(
        user_id=user_id,
        repository=repository,
    ).get("/api/v2/preferences")

    assert response.status_code == 200
    assert response.json() == {
        "value_of_time_per_hour": None,
    }

    assert repository.get_requests == [user_id]


def test_patch_preferences_persists_exact_decimal() -> None:
    user_id = UserId(value=uuid4())

    repository = RecordingPreferencesRepository()

    response = _test_client(
        user_id=user_id,
        repository=repository,
    ).patch(
        "/api/v2/preferences",
        json={
            "value_of_time_per_hour": "37.125",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "value_of_time_per_hour": "37.125",
    }

    assert repository.save_requests == [
        (
            user_id,
            UserPreferences(value_of_time_per_hour=Decimal("37.125")),
        )
    ]


def test_patch_preferences_can_clear_value() -> None:
    user_id = UserId(value=uuid4())

    repository = RecordingPreferencesRepository()

    repository.preferences[user_id] = UserPreferences(value_of_time_per_hour=Decimal(42))

    response = _test_client(
        user_id=user_id,
        repository=repository,
    ).patch(
        "/api/v2/preferences",
        json={
            "value_of_time_per_hour": None,
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "value_of_time_per_hour": None,
    }


def test_patch_preferences_rejects_negative_value() -> None:
    user_id = UserId(value=uuid4())

    repository = RecordingPreferencesRepository()

    response = _test_client(
        user_id=user_id,
        repository=repository,
    ).patch(
        "/api/v2/preferences",
        json={
            "value_of_time_per_hour": "-0.01",
        },
    )

    assert response.status_code == 422
    assert repository.save_requests == []


def test_patch_preferences_rejects_client_supplied_user_id() -> None:
    authenticated_user = UserId(value=uuid4())

    repository = RecordingPreferencesRepository()

    response = _test_client(
        user_id=authenticated_user,
        repository=repository,
    ).patch(
        "/api/v2/preferences",
        json={
            "user_id": str(uuid4()),
            "value_of_time_per_hour": "25",
        },
    )

    assert response.status_code == 422
    assert repository.save_requests == []


def test_preferences_are_scoped_to_authenticated_user() -> None:
    first_user = UserId(value=uuid4())

    second_user = UserId(value=uuid4())

    repository = RecordingPreferencesRepository()

    first_client = _test_client(
        user_id=first_user,
        repository=repository,
    )

    second_client = _test_client(
        user_id=second_user,
        repository=repository,
    )

    first_response = first_client.patch(
        "/api/v2/preferences",
        json={
            "value_of_time_per_hour": "20",
        },
    )

    second_response = second_client.patch(
        "/api/v2/preferences",
        json={
            "value_of_time_per_hour": "80",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert repository.preferences[first_user].value_of_time_per_hour == Decimal(20)

    assert repository.preferences[second_user].value_of_time_per_hour == Decimal(80)
