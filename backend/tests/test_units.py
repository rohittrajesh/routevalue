from decimal import Decimal

from routevalue.domain.units import meters_to_miles, seconds_to_hours


def test_seconds_to_hours_converts_one_hour() -> None:
    assert seconds_to_hours(3600) == Decimal(1)


def test_seconds_to_hours_preserves_fractional_hours() -> None:
    assert seconds_to_hours(90) == Decimal("0.025")


def test_meters_to_miles_converts_known_distance() -> None:
    assert meters_to_miles(804_672) == Decimal(500)


def test_conversions_return_decimal_values() -> None:
    assert seconds_to_hours(3600) == Decimal(1)
    assert meters_to_miles(804_672) == Decimal(500)