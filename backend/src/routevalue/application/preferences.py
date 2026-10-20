"""Provider-neutral persisted user preferences."""

from dataclasses import dataclass
from decimal import Decimal

from routevalue.application.models import ResolvedLocation
from routevalue.domain.identity import SavedVehicleId
from routevalue.domain.units import MoneyPerHour, MoneyPerKilowattHour


@dataclass(frozen=True, slots=True)
class PreferredFuelMarket:
    """User-selected purchasing area, not a provider-derived pricing region."""

    display_name: str
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if len(self.display_name) > 200:
            raise ValueError("fuel market name must not exceed 200 characters")
        self.to_location()  # Reuse finite geographic coordinate/name validation.

    def to_location(self) -> ResolvedLocation:
        return ResolvedLocation(self.display_name, self.latitude, self.longitude)


@dataclass(frozen=True, slots=True)
class UserPreferences:
    """Persisted personalization settings for one RouteValue user."""

    value_of_time_per_hour: MoneyPerHour | None = None
    default_vehicle_id: SavedVehicleId | None = None
    electricity_price_per_kwh: MoneyPerKilowattHour | None = None
    preferred_fuel_market: PreferredFuelMarket | None = None

    def __post_init__(self) -> None:
        rate = self.electricity_price_per_kwh
        if rate is not None:
            if not isinstance(rate, Decimal):
                raise TypeError("electricity price must be a Decimal")
            if not rate.is_finite() or rate < 0:
                raise ValueError("electricity price must be finite and nonnegative")
        if self.preferred_fuel_market is not None and not isinstance(
            self.preferred_fuel_market, PreferredFuelMarket
        ):
            raise TypeError("preferred fuel market must be a PreferredFuelMarket")
        if self.value_of_time_per_hour is not None and self.value_of_time_per_hour < 0:
            raise ValueError("value_of_time_per_hour cannot be negative")

        if self.default_vehicle_id is not None and not isinstance(
            self.default_vehicle_id,
            SavedVehicleId,
        ):
            raise TypeError("default_vehicle_id must be a SavedVehicleId")
