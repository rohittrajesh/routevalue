"""Tests for authenticated V2 preference resources."""

from dataclasses import replace as replace_preferences
from decimal import Decimal
from typing import cast
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routevalue.api.errors import (
    SavedVehicleNotFoundError,
    saved_vehicle_not_found_error_handler,
)
from routevalue.api.preferences import (
    get_user_preferences_repository,
    router,
)
from routevalue.api.saved_vehicles import (
    get_saved_vehicle_repository,
)
from routevalue.api.user_identity import (
    get_authenticated_user,
)
from routevalue.application.identity import (
    AuthenticatedUser,
)
from routevalue.application.preferences import (
    UserPreferences,
    UserPreferencesPatch,
)
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleSnapshot,
)
from routevalue.domain.identity import (
    SavedVehicleId,
    UserId,
)


class RecordingPreferencesRepository:
    """In-memory repository that records internal-user ownership."""

    def __init__(self) -> None:
        self.preferences: dict[
            UserId,
            UserPreferences,
        ] = {}

        self.get_requests: list[UserId] = []

        self.save_requests: list[
            tuple[
                UserId,
                UserPreferences,
            ]
        ] = []

    def get_preferences(
        self,
        user_id: UserId,
    ) -> UserPreferences:
        self.get_requests.append(user_id)

        return self.preferences.get(
            user_id,
            UserPreferences(),
        )

    def update_preferences(self, user_id: UserId, changes: UserPreferencesPatch) -> UserPreferences:
        current = self.get_preferences(user_id)
        updated = replace_preferences(current, **changes)
        if updated == current:
            return current
        return self.save_preferences(user_id, updated)

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


class RecordingSavedVehicleRepository:
    """Minimal ownership-aware saved-vehicle repository."""

    def __init__(self) -> None:
        self.owned_ids: dict[
            UserId,
            set[SavedVehicleId],
        ] = {}

    def list_vehicles(
        self,
        user_id: UserId,
    ) -> tuple[SavedVehicle, ...]:
        del user_id

        return ()

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        if vehicle_id not in self.owned_ids.get(
            user_id,
            set(),
        ):
            return None

        return cast(
            SavedVehicle,
            object(),
        )

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        del user_id
        del snapshot

        raise AssertionError("create_vehicle should not be called")

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        del user_id
        del vehicle_id

        return False


def _test_client(
    *,
    user_id: UserId,
    repository: RecordingPreferencesRepository,
    saved_vehicle_repository: (RecordingSavedVehicleRepository | None) = None,
) -> TestClient:
    app = FastAPI()

    app.include_router(router)

    app.add_exception_handler(
        SavedVehicleNotFoundError,
        saved_vehicle_not_found_error_handler,
    )

    vehicle_repository = saved_vehicle_repository or RecordingSavedVehicleRepository()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)

    app.dependency_overrides[get_user_preferences_repository] = lambda: repository

    app.dependency_overrides[get_saved_vehicle_repository] = lambda: vehicle_repository

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
        "default_vehicle_id": None,
        "electricity_price_per_kwh": None,
        "preferred_fuel_market": None,
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
            "value_of_time_per_hour": ("37.125"),
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "value_of_time_per_hour": "37.125",
        "default_vehicle_id": None,
        "electricity_price_per_kwh": None,
        "preferred_fuel_market": None,
    }

    assert repository.save_requests == [
        (
            user_id,
            UserPreferences(value_of_time_per_hour=(Decimal("37.125"))),
        )
    ]


def test_patch_preferences_can_clear_value() -> None:
    user_id = UserId(value=uuid4())

    repository = RecordingPreferencesRepository()

    repository.preferences[user_id] = UserPreferences(value_of_time_per_hour=(Decimal(42)))

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
        "default_vehicle_id": None,
        "electricity_price_per_kwh": None,
        "preferred_fuel_market": None,
    }


def test_patch_preferences_can_set_owned_default_vehicle() -> None:
    user_id = UserId(value=uuid4())

    vehicle_id = SavedVehicleId(value=uuid4())

    repository = RecordingPreferencesRepository()

    vehicle_repository = RecordingSavedVehicleRepository()

    vehicle_repository.owned_ids[user_id] = {
        vehicle_id,
    }

    response = _test_client(
        user_id=user_id,
        repository=repository,
        saved_vehicle_repository=(vehicle_repository),
    ).patch(
        "/api/v2/preferences",
        json={
            "default_vehicle_id": (str(vehicle_id.value)),
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "value_of_time_per_hour": None,
        "default_vehicle_id": (str(vehicle_id.value)),
        "electricity_price_per_kwh": None,
        "preferred_fuel_market": None,
    }

    assert repository.preferences[user_id].default_vehicle_id == vehicle_id


def test_patch_preferences_can_clear_default_vehicle() -> None:
    user_id = UserId(value=uuid4())

    vehicle_id = SavedVehicleId(value=uuid4())

    repository = RecordingPreferencesRepository()

    repository.preferences[user_id] = UserPreferences(
        value_of_time_per_hour=(Decimal(25)),
        default_vehicle_id=vehicle_id,
    )

    response = _test_client(
        user_id=user_id,
        repository=repository,
    ).patch(
        "/api/v2/preferences",
        json={
            "default_vehicle_id": None,
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "value_of_time_per_hour": "25",
        "default_vehicle_id": None,
        "electricity_price_per_kwh": None,
        "preferred_fuel_market": None,
    }


def test_patch_preferences_hides_foreign_default_vehicle() -> None:
    authenticated_user = UserId(value=uuid4())

    other_user = UserId(value=uuid4())

    vehicle_id = SavedVehicleId(value=uuid4())

    repository = RecordingPreferencesRepository()

    vehicle_repository = RecordingSavedVehicleRepository()

    vehicle_repository.owned_ids[other_user] = {
        vehicle_id,
    }

    response = _test_client(
        user_id=authenticated_user,
        repository=repository,
        saved_vehicle_repository=(vehicle_repository),
    ).patch(
        "/api/v2/preferences",
        json={
            "default_vehicle_id": (str(vehicle_id.value)),
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "code": "saved_vehicle_not_found",
        "detail": ("Saved vehicle was not found."),
    }

    assert repository.save_requests == []


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


def test_patch_preferences_rejects_empty_update() -> None:
    user_id = UserId(value=uuid4())

    repository = RecordingPreferencesRepository()

    response = _test_client(
        user_id=user_id,
        repository=repository,
    ).patch(
        "/api/v2/preferences",
        json={},
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
