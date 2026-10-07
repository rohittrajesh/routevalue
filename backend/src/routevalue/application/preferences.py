"""Provider-neutral persisted user preferences."""

from dataclasses import dataclass

from routevalue.domain.units import MoneyPerHour


@dataclass(frozen=True, slots=True)
class UserPreferences:
    """Persisted personalization settings for one RouteValue user."""

    value_of_time_per_hour: MoneyPerHour | None = None

    def __post_init__(self) -> None:
        if self.value_of_time_per_hour is not None and self.value_of_time_per_hour < 0:
            raise ValueError("value_of_time_per_hour cannot be negative")
