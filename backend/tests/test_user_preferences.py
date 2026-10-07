"""Tests for provider-neutral persistent user preferences."""

from decimal import Decimal
from uuid import uuid4

import pytest

from routevalue.application.ports import UserPreferencesRepository
from routevalue.application.preferences import UserPreferences
from routevalue.application.user_preferences import (
    UserPreferencesService,
)
from routevalue.domain.identity import UserId


class FakeUserPreferencesRepository:
    """In-memory preferences repository for application tests."""

    def __init__(self) -> None:
        self._preferences: dict[
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

        return self._preferences.get(
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

        self._preferences[user_id] = preferences

        return preferences


def _user_id() -> UserId:
    return UserId(value=uuid4())


def _service(
    repository: UserPreferencesRepository,
) -> UserPreferencesService:
    return UserPreferencesService(
        repository=repository,
    )


def test_new_user_preferences_are_unset() -> None:
    repository = FakeUserPreferencesRepository()

    preferences = _service(repository).get_preferences(_user_id())

    assert preferences == UserPreferences()
    assert preferences.value_of_time_per_hour is None


def test_preferences_accept_exact_decimal_value_of_time() -> None:
    preferences = UserPreferences(value_of_time_per_hour=Decimal("27.125"))

    assert preferences.value_of_time_per_hour == Decimal("27.125")


def test_preferences_reject_negative_value_of_time() -> None:
    with pytest.raises(
        ValueError,
        match="value_of_time_per_hour cannot be negative",
    ):
        UserPreferences(value_of_time_per_hour=Decimal("-0.01"))


def test_service_persists_value_of_time_for_correct_user() -> None:
    repository = FakeUserPreferencesRepository()
    service = _service(repository)

    user_id = _user_id()

    result = service.set_value_of_time(
        user_id,
        Decimal("35.50"),
    )

    assert result == UserPreferences(value_of_time_per_hour=Decimal("35.50"))

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
