"""M7-C tests for pure gravitational energy calculations."""

from decimal import Decimal

import pytest

from routevalue.domain.gravitational_energy import (
    JOULES_PER_KILOWATT_HOUR,
    STANDARD_GRAVITY_METERS_PER_SECOND_SQUARED,
    gravitational_energy_kwh,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


def _mass(kilograms: str = "1000") -> VehicleMass:
    return VehicleMass(
        kilograms=Decimal(kilograms),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
    )


def test_physical_constants_are_explicit() -> None:
    assert STANDARD_GRAVITY_METERS_PER_SECOND_SQUARED == Decimal("9.80665")
    assert JOULES_PER_KILOWATT_HOUR == Decimal(3600000)


def test_uphill_gravitational_energy() -> None:
    result = gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(100),
    )

    expected = Decimal(1000) * Decimal("9.80665") * Decimal(100) / Decimal(3600000)

    assert result == expected
    assert result > 0


def test_downhill_energy_is_negative() -> None:
    result = gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(-100),
    )

    assert result < 0
    assert result == -gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(100),
    )


def test_flat_terrain_has_exactly_zero_gravitational_energy() -> None:
    result = gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(0),
    )

    assert result == Decimal(0)


def test_gravitational_energy_scales_linearly_with_mass() -> None:
    lighter = gravitational_energy_kwh(
        vehicle_mass=_mass("1000"),
        elevation_change_meters=Decimal(100),
    )

    heavier = gravitational_energy_kwh(
        vehicle_mass=_mass("2000"),
        elevation_change_meters=Decimal(100),
    )

    assert abs(heavier - lighter * 2) < Decimal("1e-24")


def test_gravitational_energy_scales_linearly_with_elevation() -> None:
    first = gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(100),
    )

    second = gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(200),
    )

    assert abs(second - first * 2) < Decimal("1e-24")


def test_equal_uphill_and_downhill_cancel_mechanical_energy() -> None:
    climb = gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(100),
    )

    descent = gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(-100),
    )

    assert climb + descent == Decimal(0)


def test_fractional_elevation_preserves_decimal_precision() -> None:
    result = gravitational_energy_kwh(
        vehicle_mass=_mass("1825.75"),
        elevation_change_meters=Decimal("37.125"),
    )

    expected = Decimal("1825.75") * Decimal("9.80665") * Decimal("37.125") / Decimal(3600000)

    assert result == expected


@pytest.mark.parametrize(
    "invalid_elevation",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_nonfinite_elevations_are_rejected(
    invalid_elevation: Decimal,
) -> None:
    with pytest.raises(ValueError):
        gravitational_energy_kwh(
            vehicle_mass=_mass(),
            elevation_change_meters=invalid_elevation,
        )


def test_invalid_elevation_type_is_rejected() -> None:
    with pytest.raises(TypeError):
        gravitational_energy_kwh(
            vehicle_mass=_mass(),
            elevation_change_meters=100,  # type: ignore[arg-type]
        )


def test_invalid_vehicle_mass_type_is_rejected() -> None:
    with pytest.raises(TypeError):
        gravitational_energy_kwh(
            vehicle_mass=None,  # type: ignore[arg-type]
            elevation_change_meters=Decimal(100),
        )


def test_calculation_is_deterministic_and_nonmutating() -> None:
    mass = _mass("1750.5")
    original_mass = mass.kilograms

    first = gravitational_energy_kwh(
        vehicle_mass=mass,
        elevation_change_meters=Decimal(250),
    )

    second = gravitational_energy_kwh(
        vehicle_mass=mass,
        elevation_change_meters=Decimal(250),
    )

    assert first == second
    assert mass.kilograms == original_mass
