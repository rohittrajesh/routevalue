"""Application service for persistent RouteValue user preferences."""

from dataclasses import dataclass

from routevalue.application.ports import UserPreferencesRepository
from routevalue.application.preferences import UserPreferences
from routevalue.domain.identity import UserId
from routevalue.domain.units import MoneyPerHour


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

    def set_value_of_time(
        self,
        user_id: UserId,
        value_of_time_per_hour: MoneyPerHour | None,
    ) -> UserPreferences:
        """Persist a new value of time, or clear the existing value."""

        current = self.repository.get_preferences(user_id)

        updated = UserPreferences(
            value_of_time_per_hour=value_of_time_per_hour,
        )

        if updated == current:
            return current

        return self.repository.save_preferences(
            user_id,
            updated,
        )
