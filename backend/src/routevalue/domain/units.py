"""Canonical units used by the RouteValue domain."""

from decimal import Decimal

type Meters = int
type Seconds = int

type Money = Decimal
type MoneyPerHour = Decimal

type Gallons = Decimal
type MilesPerGallon = Decimal
type MoneyPerGallon = Decimal

type KilowattHours = Decimal
type KilowattHoursPerMile = Decimal
type MoneyPerKilowattHour = Decimal

SECONDS_PER_HOUR = Decimal(3600)
METERS_PER_MILE = Decimal("1609.344")


def seconds_to_hours(seconds: Seconds) -> Decimal:
    """Convert seconds to hours using exact decimal arithmetic."""
    return Decimal(seconds) / SECONDS_PER_HOUR


def meters_to_miles(meters: Meters) -> Decimal:
    """Convert meters to miles using exact decimal arithmetic."""
    return Decimal(meters) / METERS_PER_MILE
