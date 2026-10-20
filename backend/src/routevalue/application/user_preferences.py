"""Application services for persistent RouteValue user preferences."""

from dataclasses import dataclass

from routevalue.application.ports import (
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.preferences import UserPreferences, UserPreferencesPatch
from routevalue.domain.identity import (
    SavedVehicleId,
    UserId,
)
from routevalue.domain.units import MoneyPerHour


class DefaultVehicleUnavailableError(ValueError):
    """Raised when a requested default vehicle is outside the user's ownership scope."""


@dataclass(frozen=True, slots=True)
class UserPreferencesService:
    """Read and update personalization for one internal user."""

    repository: UserPreferencesRepository

    def get_preferences(
        self,
        user_id: UserId,
    ) -> UserPreferences:
        """Return the user's current persisted preferences."""

        return self.repository.get_preferences(user_id)

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        """Persist one complete preference state only when it changed."""

        current = self.repository.get_preferences(user_id)

        if preferences == current:
            return current

        return self.repository.save_preferences(
            user_id,
            preferences,
        )

    def set_value_of_time(
        self,
        user_id: UserId,
        value_of_time_per_hour: MoneyPerHour | None,
    ) -> UserPreferences:
        """Persist a new value of time while preserving other preferences."""

        return self.update_preferences(user_id, {"value_of_time_per_hour": value_of_time_per_hour})

    def update_preferences(self, user_id: UserId, changes: UserPreferencesPatch) -> UserPreferences:
        """Validate and apply a sparse update without reading a stale snapshot."""

        UserPreferences(**changes)
        return self.repository.update_preferences(user_id, changes)


@dataclass(frozen=True, slots=True)
class UserDefaultVehicleService:
    """Manage the user's default vehicle with ownership validation."""

    preferences_repository: UserPreferencesRepository
    saved_vehicle_repository: SavedVehicleRepository

    def validate_default_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId | None,
    ) -> None:
        """Require a non-null default vehicle to belong to the user."""

        if vehicle_id is None:
            return

        if (
            self.saved_vehicle_repository.get_vehicle(
                user_id,
                vehicle_id,
            )
            is None
        ):
            raise DefaultVehicleUnavailableError(
                "default vehicle is not available inside the user's ownership scope"
            )

    def set_default_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId | None,
    ) -> UserPreferences:
        """Set or clear the user's default saved vehicle."""

        self.validate_default_vehicle(
            user_id,
            vehicle_id,
        )

        return self.preferences_repository.update_preferences(
            user_id, {"default_vehicle_id": vehicle_id}
        )
