"""Provider-neutral persisted user preferences."""

from dataclasses import dataclass

from routevalue.domain.identity import SavedVehicleId
from routevalue.domain.units import MoneyPerHour


@dataclass(frozen=True, slots=True)
class UserPreferences:
    """Persisted personalization settings for one RouteValue user."""

    value_of_time_per_hour: MoneyPerHour | None = None
    default_vehicle_id: SavedVehicleId | None = None

    def __post_init__(self) -> None:
        if self.value_of_time_per_hour is not None and self.value_of_time_per_hour < 0:
            raise ValueError("value_of_time_per_hour cannot be negative")

        if self.default_vehicle_id is not None and not isinstance(
            self.default_vehicle_id,
            SavedVehicleId,
        ):
            raise TypeError("default_vehicle_id must be a SavedVehicleId")
