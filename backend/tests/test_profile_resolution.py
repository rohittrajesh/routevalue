"""Tests for provider-neutral V2 evaluation profile resolution."""

from dataclasses import replace as replace_preferences
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from routevalue.application.models import VehicleCatalogConfiguration
from routevalue.application.preferences import UserPreferences, UserPreferencesPatch
from routevalue.application.profile_resolution import (
    ProfileResolutionError,
    ProfileResolutionFailureReason,
    ProfileResolutionService,
)
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleSnapshot,
)
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    VehicleEnergySpecification,
)


class FakePreferencesRepository:
    """Record reads and reject unexpected profile writes."""

    def __init__(
        self,
        preferences: dict[UserId, UserPreferences],
    ) -> None:
        self.preferences = preferences
        self.get_calls: list[UserId] = []

    def get_preferences(
        self,
        user_id: UserId,
    ) -> UserPreferences:
        self.get_calls.append(user_id)

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
        raise AssertionError("profile resolution must not write preferences")


class FakeSavedVehicleRepository:
    """Enforce vehicle ownership in an in-memory test repository."""

    def __init__(
        self,
        vehicles: dict[
            tuple[UserId, SavedVehicleId],
            SavedVehicle,
        ],
    ) -> None:
        self.vehicles = vehicles
        self.get_calls: list[tuple[UserId, SavedVehicleId]] = []

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        self.get_calls.append((user_id, vehicle_id))

        return self.vehicles.get((user_id, vehicle_id))

    def list_vehicles(
        self,
        user_id: UserId,
    ) -> tuple[SavedVehicle, ...]:
        raise AssertionError("profile resolution must not list vehicles")

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        raise AssertionError("profile resolution must not create vehicles")

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        raise AssertionError("profile resolution must not delete vehicles")


def _gasoline_specification() -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal("32.125"),
        city_mpg=Decimal("28.5"),
        highway_mpg=Decimal("38.25"),
        fuel_grade=GasolineGrade.REGULAR,
    )


def _saved_vehicle(
    vehicle_id: SavedVehicleId,
    *,
    specification: VehicleEnergySpecification | None = None,
) -> SavedVehicle:
    if specification is None:
        specification = _gasoline_specification()

    return SavedVehicle(
        id=vehicle_id,
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Toyota",
            model="Camry",
            configuration="2.5L 4cyl CVT (FWD)",
            source="fueleconomy_gov",
            source_id="12345",
        ),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 1, tzinfo=UTC),
        saved_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


def _setup(
    *,
    preferences: dict[UserId, UserPreferences],
    vehicles: dict[
        tuple[UserId, SavedVehicleId],
        SavedVehicle,
    ],
) -> tuple[
    ProfileResolutionService,
    FakePreferencesRepository,
    FakeSavedVehicleRepository,
]:
    preferences_repository = FakePreferencesRepository(preferences)

    vehicle_repository = FakeSavedVehicleRepository(vehicles)

    service = ProfileResolutionService(
        preferences_repository=preferences_repository,
        saved_vehicle_repository=vehicle_repository,
    )

    return (
        service,
        preferences_repository,
        vehicle_repository,
    )


def test_resolves_default_vehicle_and_stored_value_of_time() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())
    vehicle = _saved_vehicle(vehicle_id)

    service, preferences_repo, vehicle_repo = _setup(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal("27.125"),
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={(user_id, vehicle_id): vehicle},
    )

    resolved = service.resolve_profile(user_id)

    assert resolved.value_of_time_per_hour == Decimal("27.125")
    assert resolved.saved_vehicle is vehicle
    assert preferences_repo.get_calls == [user_id]
    assert vehicle_repo.get_calls == [(user_id, vehicle_id)]


def test_explicit_vehicle_overrides_default() -> None:
    user_id = UserId(value=uuid4())

    default_id = SavedVehicleId(value=uuid4())
    requested_id = SavedVehicleId(value=uuid4())

    default_vehicle = _saved_vehicle(default_id)
    requested_vehicle = _saved_vehicle(requested_id)

    service, _, vehicle_repo = _setup(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(40),
                default_vehicle_id=default_id,
            )
        },
        vehicles={
            (user_id, default_id): default_vehicle,
            (user_id, requested_id): requested_vehicle,
        },
    )

    resolved = service.resolve_profile(
        user_id,
        requested_vehicle_id=requested_id,
    )

    assert resolved.saved_vehicle is requested_vehicle
    assert resolved.value_of_time_per_hour == Decimal(40)
    assert vehicle_repo.get_calls == [(user_id, requested_id)]


def test_explicit_vehicle_works_without_default() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())
    vehicle = _saved_vehicle(vehicle_id)

    service, _, _ = _setup(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(25),
                default_vehicle_id=None,
            )
        },
        vehicles={(user_id, vehicle_id): vehicle},
    )

    resolved = service.resolve_profile(
        user_id,
        requested_vehicle_id=vehicle_id,
    )

    assert resolved.saved_vehicle is vehicle


def test_missing_value_of_time_is_structured_failure() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, _, vehicle_repo = _setup(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=None,
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={(user_id, vehicle_id): _saved_vehicle(vehicle_id)},
    )

    with pytest.raises(ProfileResolutionError) as error:
        service.resolve_profile(user_id)

    assert error.value.reason is (ProfileResolutionFailureReason.VALUE_OF_TIME_NOT_CONFIGURED)

    assert vehicle_repo.get_calls == []


def test_zero_value_of_time_is_valid() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, _, _ = _setup(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(0),
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={(user_id, vehicle_id): _saved_vehicle(vehicle_id)},
    )

    resolved = service.resolve_profile(user_id)

    assert resolved.value_of_time_per_hour == Decimal(0)


def test_missing_default_is_structured_failure() -> None:
    user_id = UserId(value=uuid4())

    service, _, vehicle_repo = _setup(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(25),
                default_vehicle_id=None,
            )
        },
        vehicles={},
    )

    with pytest.raises(ProfileResolutionError) as error:
        service.resolve_profile(user_id)

    assert error.value.reason is (ProfileResolutionFailureReason.DEFAULT_VEHICLE_NOT_CONFIGURED)

    assert vehicle_repo.get_calls == []


def test_unknown_explicit_vehicle_does_not_fall_back() -> None:
    user_id = UserId(value=uuid4())

    default_id = SavedVehicleId(value=uuid4())
    requested_id = SavedVehicleId(value=uuid4())

    service, _, vehicle_repo = _setup(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(25),
                default_vehicle_id=default_id,
            )
        },
        vehicles={(user_id, default_id): _saved_vehicle(default_id)},
    )

    with pytest.raises(ProfileResolutionError) as error:
        service.resolve_profile(
            user_id,
            requested_vehicle_id=requested_id,
        )

    assert error.value.reason is (ProfileResolutionFailureReason.SAVED_VEHICLE_NOT_FOUND)

    assert vehicle_repo.get_calls == [(user_id, requested_id)]


def test_foreign_vehicle_is_not_accessible() -> None:
    user_id = UserId(value=uuid4())
    other_user = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, _, vehicle_repo = _setup(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(25),
            )
        },
        vehicles={(other_user, vehicle_id): _saved_vehicle(vehicle_id)},
    )

    with pytest.raises(ProfileResolutionError) as error:
        service.resolve_profile(
            user_id,
            requested_vehicle_id=vehicle_id,
        )

    assert error.value.reason is (ProfileResolutionFailureReason.SAVED_VEHICLE_NOT_FOUND)

    assert vehicle_repo.get_calls == [(user_id, vehicle_id)]


def test_stale_default_vehicle_is_distinct_failure() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, _, vehicle_repo = _setup(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(25),
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={},
    )

    with pytest.raises(ProfileResolutionError) as error:
        service.resolve_profile(user_id)

    assert error.value.reason is (ProfileResolutionFailureReason.DEFAULT_VEHICLE_UNAVAILABLE)

    assert vehicle_repo.get_calls == [(user_id, vehicle_id)]


def test_multiple_users_remain_isolated() -> None:
    first_user = UserId(value=uuid4())
    second_user = UserId(value=uuid4())

    first_id = SavedVehicleId(value=uuid4())
    second_id = SavedVehicleId(value=uuid4())

    first_vehicle = _saved_vehicle(first_id)
    second_vehicle = _saved_vehicle(second_id)

    service, preferences_repo, vehicle_repo = _setup(
        preferences={
            first_user: UserPreferences(
                value_of_time_per_hour=Decimal(15),
                default_vehicle_id=first_id,
            ),
            second_user: UserPreferences(
                value_of_time_per_hour=Decimal(80),
                default_vehicle_id=second_id,
            ),
        },
        vehicles={
            (first_user, first_id): first_vehicle,
            (second_user, second_id): second_vehicle,
        },
    )

    first_result = service.resolve_profile(first_user)
    second_result = service.resolve_profile(second_user)

    assert first_result.saved_vehicle is first_vehicle
    assert first_result.value_of_time_per_hour == Decimal(15)

    assert second_result.saved_vehicle is second_vehicle
    assert second_result.value_of_time_per_hour == Decimal(80)

    assert preferences_repo.get_calls == [
        first_user,
        second_user,
    ]

    assert vehicle_repo.get_calls == [
        (first_user, first_id),
        (second_user, second_id),
    ]


def test_bev_snapshot_can_resolve_without_evaluation() -> None:
    """M4 profile resolution stays reusable for future BEV evaluation."""

    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    specification = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.285"),
    )

    vehicle = _saved_vehicle(
        vehicle_id,
        specification=specification,
    )

    service, _, _ = _setup(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(30),
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={(user_id, vehicle_id): vehicle},
    )

    resolved = service.resolve_profile(user_id)

    assert resolved.saved_vehicle.specification is specification


def test_persistence_failures_are_not_silently_hidden() -> None:
    """Infrastructure failures must remain visible to later API mapping."""

    user_id = UserId(value=uuid4())

    class FailingPreferencesRepository(FakePreferencesRepository):
        def get_preferences(
            self,
            user_id: UserId,
        ) -> UserPreferences:
            raise RuntimeError("simulated database failure")

    service = ProfileResolutionService(
        preferences_repository=FailingPreferencesRepository({}),
        saved_vehicle_repository=FakeSavedVehicleRepository({}),
    )

    with pytest.raises(RuntimeError, match="simulated database failure"):
        service.resolve_profile(user_id)
