"""Provider-neutral profile resolution for V2 trip evaluation."""

from dataclasses import dataclass
from enum import StrEnum

from routevalue.application.ports import (
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.units import MoneyPerHour


class ProfileResolutionFailureReason(StrEnum):
    """Structured reasons an evaluation profile cannot be resolved."""

    VALUE_OF_TIME_NOT_CONFIGURED = "value_of_time_not_configured"
    DEFAULT_VEHICLE_NOT_CONFIGURED = "default_vehicle_not_configured"
    DEFAULT_VEHICLE_UNAVAILABLE = "default_vehicle_unavailable"
    SAVED_VEHICLE_NOT_FOUND = "saved_vehicle_not_found"


class ProfileResolutionError(RuntimeError):
    """A required persisted evaluation-profile value is unavailable."""

    def __init__(
        self,
        reason: ProfileResolutionFailureReason,
    ) -> None:
        self.reason = reason
        super().__init__(reason.value)


@dataclass(frozen=True, slots=True)
class ResolvedEvaluationProfile:
    """Persisted personalization required for one trip evaluation."""

    value_of_time_per_hour: MoneyPerHour
    saved_vehicle: SavedVehicle


@dataclass(frozen=True, slots=True)
class ProfileResolutionService:
    """Resolve an owned saved vehicle and stored value of time."""

    preferences_repository: UserPreferencesRepository
    saved_vehicle_repository: SavedVehicleRepository

    def resolve_profile(
        self,
        user_id: UserId,
        *,
        requested_vehicle_id: SavedVehicleId | None = None,
    ) -> ResolvedEvaluationProfile:
        """Resolve a user's complete persisted evaluation profile.

        An explicit vehicle takes precedence over the persisted default.
        Every vehicle lookup is scoped to the internal authenticated user.
        """

        preferences = self.preferences_repository.get_preferences(user_id)

        value_of_time = preferences.value_of_time_per_hour

        if value_of_time is None:
            raise ProfileResolutionError(
                ProfileResolutionFailureReason.VALUE_OF_TIME_NOT_CONFIGURED
            )

        vehicle_id = requested_vehicle_id

        if vehicle_id is None:
            vehicle_id = preferences.default_vehicle_id

            if vehicle_id is None:
                raise ProfileResolutionError(
                    ProfileResolutionFailureReason.DEFAULT_VEHICLE_NOT_CONFIGURED
                )

        vehicle = self.saved_vehicle_repository.get_vehicle(
            user_id,
            vehicle_id,
        )

        if vehicle is None:
            if requested_vehicle_id is not None:
                reason = ProfileResolutionFailureReason.SAVED_VEHICLE_NOT_FOUND
            else:
                reason = ProfileResolutionFailureReason.DEFAULT_VEHICLE_UNAVAILABLE

            raise ProfileResolutionError(reason)

        return ResolvedEvaluationProfile(
            value_of_time_per_hour=value_of_time,
            saved_vehicle=vehicle,
        )
