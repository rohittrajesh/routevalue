"""Tests for provider-neutral persistent user preferences."""

from dataclasses import replace as replace_preferences
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest

from routevalue.application.ports import (
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.preferences import (
    UserPreferences,
    UserPreferencesPatch,
)
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleSnapshot,
)
from routevalue.application.user_preferences import (
    DefaultVehicleUnavailableError,
    UserDefaultVehicleService,
    UserPreferencesService,
)
from routevalue.domain.identity import (
    SavedVehicleId,
    UserId,
)


class FakeUserPreferencesRepository:
    """In-memory preferences repository for application tests."""

    def __init__(self) -> None:
        self._preferences: dict[
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

        return self._preferences.get(
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

        self._preferences[user_id] = preferences

        return preferences


class FakeSavedVehicleRepository:
    """Minimal ownership-aware saved-vehicle repository."""

    def __init__(self) -> None:
        self.owned_ids: dict[
            UserId,
            set[SavedVehicleId],
        ] = {}

        self.get_requests: list[
            tuple[
                UserId,
                SavedVehicleId,
            ]
        ] = []

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
        self.get_requests.append(
            (
                user_id,
                vehicle_id,
            )
        )

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


def _user_id() -> UserId:
    return UserId(value=uuid4())


def _saved_vehicle_id() -> SavedVehicleId:
    return SavedVehicleId(value=uuid4())


def _service(
    repository: UserPreferencesRepository,
) -> UserPreferencesService:
    return UserPreferencesService(
        repository=repository,
    )


def _default_vehicle_service(
    preferences_repository: UserPreferencesRepository,
    saved_vehicle_repository: SavedVehicleRepository,
) -> UserDefaultVehicleService:
    return UserDefaultVehicleService(
        preferences_repository=(preferences_repository),
        saved_vehicle_repository=(saved_vehicle_repository),
    )


def test_new_user_preferences_are_unset() -> None:
    repository = FakeUserPreferencesRepository()

    preferences = _service(repository).get_preferences(_user_id())

    assert preferences == UserPreferences()

    assert preferences.value_of_time_per_hour is None

    assert preferences.default_vehicle_id is None


def test_preferences_accept_exact_decimal_value_of_time() -> None:
    preferences = UserPreferences(value_of_time_per_hour=(Decimal("27.125")))

    assert preferences.value_of_time_per_hour == Decimal("27.125")


def test_preferences_reject_negative_value_of_time() -> None:
    with pytest.raises(
        ValueError,
        match=("value_of_time_per_hour cannot be negative"),
    ):
        UserPreferences(value_of_time_per_hour=(Decimal("-0.01")))


def test_service_persists_value_of_time_for_correct_user() -> None:
    repository = FakeUserPreferencesRepository()

    service = _service(repository)

    user_id = _user_id()

    result = service.set_value_of_time(
        user_id,
        Decimal("35.50"),
    )

    assert result == UserPreferences(value_of_time_per_hour=(Decimal("35.50")))

    assert repository.save_requests == [
        (
            user_id,
            result,
        )
    ]


def test_service_can_clear_value_of_time() -> None:
    repository = FakeUserPreferencesRepository()

    service = _service(repository)

    user_id = _user_id()

    _ = service.set_value_of_time(
        user_id,
        Decimal(42),
    )

    cleared = service.set_value_of_time(
        user_id,
        None,
    )

    assert cleared.value_of_time_per_hour is None

    assert service.get_preferences(user_id) == UserPreferences()


def test_unchanged_preferences_do_not_write_again() -> None:
    repository = FakeUserPreferencesRepository()

    service = _service(repository)

    user_id = _user_id()

    first = service.set_value_of_time(
        user_id,
        Decimal(25),
    )

    save_count = len(repository.save_requests)

    second = service.set_value_of_time(
        user_id,
        Decimal(25),
    )

    assert second == first

    assert len(repository.save_requests) == save_count


def test_preferences_are_isolated_by_internal_user_id() -> None:
    repository = FakeUserPreferencesRepository()

    service = _service(repository)

    first_user = _user_id()
    second_user = _user_id()

    _ = service.set_value_of_time(
        first_user,
        Decimal(20),
    )

    _ = service.set_value_of_time(
        second_user,
        Decimal(80),
    )

    assert service.get_preferences(first_user).value_of_time_per_hour == Decimal(20)

    assert service.get_preferences(second_user).value_of_time_per_hour == Decimal(80)


def test_value_of_time_update_preserves_default_vehicle() -> None:
    repository = FakeUserPreferencesRepository()

    service = _service(repository)

    user_id = _user_id()
    vehicle_id = _saved_vehicle_id()

    repository._preferences[user_id] = UserPreferences(
        value_of_time_per_hour=(Decimal(10)),
        default_vehicle_id=vehicle_id,
    )

    updated = service.set_value_of_time(
        user_id,
        Decimal(40),
    )

    assert updated.value_of_time_per_hour == Decimal(40)

    assert updated.default_vehicle_id == vehicle_id


def test_owned_vehicle_can_be_set_as_default() -> None:
    preferences_repository = FakeUserPreferencesRepository()

    vehicle_repository = FakeSavedVehicleRepository()

    user_id = _user_id()
    vehicle_id = _saved_vehicle_id()

    vehicle_repository.owned_ids[user_id] = {
        vehicle_id,
    }

    preferences_repository._preferences[user_id] = UserPreferences(
        value_of_time_per_hour=(Decimal("31.25"))
    )

    service = _default_vehicle_service(
        preferences_repository,
        vehicle_repository,
    )

    result = service.set_default_vehicle(
        user_id,
        vehicle_id,
    )

    assert result.value_of_time_per_hour == Decimal("31.25")

    assert result.default_vehicle_id == vehicle_id


def test_default_vehicle_can_be_cleared() -> None:
    preferences_repository = FakeUserPreferencesRepository()

    vehicle_repository = FakeSavedVehicleRepository()

    user_id = _user_id()
    vehicle_id = _saved_vehicle_id()

    preferences_repository._preferences[user_id] = UserPreferences(
        value_of_time_per_hour=(Decimal(15)),
        default_vehicle_id=vehicle_id,
    )

    service = _default_vehicle_service(
        preferences_repository,
        vehicle_repository,
    )

    result = service.set_default_vehicle(
        user_id,
        None,
    )

    assert result.value_of_time_per_hour == Decimal(15)

    assert result.default_vehicle_id is None


def test_vehicle_outside_user_scope_cannot_become_default() -> None:
    preferences_repository = FakeUserPreferencesRepository()

    vehicle_repository = FakeSavedVehicleRepository()

    first_user = _user_id()
    second_user = _user_id()
    vehicle_id = _saved_vehicle_id()

    vehicle_repository.owned_ids[second_user] = {
        vehicle_id,
    }

    service = _default_vehicle_service(
        preferences_repository,
        vehicle_repository,
    )

    with pytest.raises(
        DefaultVehicleUnavailableError,
        match=("default vehicle is not available inside the user's ownership scope"),
    ):
        service.set_default_vehicle(
            first_user,
            vehicle_id,
        )

    assert preferences_repository.save_requests == []
