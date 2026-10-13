"""M7-C2 tests for normalized terrain gravitational-energy aggregation."""

from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample, TerrainProfile
from routevalue.application.terrain_energy import (
    TerrainEnergyResult,
    calculate_terrain_gravitational_energy,
)
from routevalue.application.terrain_normalization import (
    normalize_terrain_profile,
)
from routevalue.domain.gravitational_energy import gravitational_energy_kwh
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


def _mass(kilograms: str = "1500") -> VehicleMass:
    return VehicleMass(
        kilograms=Decimal(kilograms),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
    )


def _profile(
    elevations: tuple[Decimal | None, ...],
    *,
    spacing: int = 250,
) -> TerrainProfile:
    return TerrainProfile(
        route_distance_meters=(len(elevations) - 1) * spacing,
        samples=tuple(
            ElevationSample(
                point=RoutePoint(
                    latitude=32.0,
                    longitude=-117.0,
                ),
                distance_meters=index * spacing,
                elevation_meters=elevation,
            )
            for index, elevation in enumerate(elevations)
        ),
    )


def _calculate(
    elevations: tuple[Decimal | None, ...],
    *,
    spacing: int = 250,
    mass: VehicleMass | None = None,
) -> TerrainEnergyResult:
    normalized = normalize_terrain_profile(_profile(elevations, spacing=spacing))

    return calculate_terrain_gravitational_energy(
        normalized,
        vehicle_mass=mass if mass is not None else _mass(),
    )


def test_flat_route_has_exact_zero_gravitational_energy() -> None:
    result = _calculate((Decimal(100), Decimal(100), Decimal(100)))

    assert result.is_complete
    assert result.coverage == Decimal(1)
    assert result.uphill_gravitational_kwh == 0
    assert result.downhill_gravitational_kwh == 0
    assert result.net_gravitational_kwh == 0
    assert all(segment.gravitational_kwh == 0 for segment in result.segments)


def test_uphill_route_has_positive_mechanical_energy() -> None:
    result = _calculate((Decimal(100), Decimal(110), Decimal(120)))

    expected = gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(20),
    )

    tolerance = Decimal("1e-24")

    assert abs(result.uphill_gravitational_kwh - expected) < tolerance
    assert result.downhill_gravitational_kwh == 0
    assert abs(result.net_gravitational_kwh - expected) < tolerance


def test_downhill_route_has_negative_net_energy() -> None:
    result = _calculate((Decimal(120), Decimal(110), Decimal(100)))

    expected = gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(-20),
    )

    tolerance = Decimal("1e-24")

    assert result.uphill_gravitational_kwh == 0
    assert abs(result.downhill_gravitational_kwh + expected) < tolerance
    assert abs(result.net_gravitational_kwh - expected) < tolerance


def test_uphill_and_downhill_are_preserved_separately() -> None:
    result = _calculate(
        (
            Decimal(100),
            Decimal(110),
            Decimal(120),
            Decimal(110),
            Decimal(100),
        )
    )

    # The 3-point median filter smooths the peak from 120 m to 110 m.
    # Therefore, the normalized route climbs 10 m and descends 10 m.
    expected = gravitational_energy_kwh(
        vehicle_mass=_mass(),
        elevation_change_meters=Decimal(10),
    )

    tolerance = Decimal("1e-24")

    assert abs(result.uphill_gravitational_kwh - expected) < tolerance
    assert abs(result.downhill_gravitational_kwh - expected) < tolerance
    assert abs(result.net_gravitational_kwh) < tolerance

    assert result.uphill_gravitational_kwh > 0
    assert result.downhill_gravitational_kwh > 0


def test_partial_terrain_preserves_unknown_energy() -> None:
    result = _calculate(
        (
            Decimal(100),
            Decimal(110),
            Decimal(120),
            None,
            None,
        )
    )

    assert result.route_distance_meters == 1000
    assert result.usable_distance_meters == 500
    assert result.unknown_distance_meters == 500
    assert result.coverage == Decimal("0.5")
    assert not result.is_complete

    assert result.segments[0].is_usable
    assert result.segments[1].is_usable
    assert result.segments[2].gravitational_kwh is None
    assert result.segments[3].gravitational_kwh is None


def test_missing_terrain_is_not_treated_as_flat() -> None:
    result = _calculate((Decimal(100), None, Decimal(100)))

    assert result.coverage == 0
    assert not result.is_complete
    assert all(segment.gravitational_kwh is None for segment in result.segments)


def test_extreme_grade_is_excluded_from_energy() -> None:
    result = _calculate((Decimal(100), Decimal(200)))

    assert result.coverage == 0
    assert result.segments[0].gravitational_kwh is None
    assert result.uphill_gravitational_kwh == 0


def test_calculation_scales_with_vehicle_mass() -> None:
    elevations = (Decimal(100), Decimal(120))

    lighter = _calculate(elevations, mass=_mass("1000"))
    heavier = _calculate(elevations, mass=_mass("2000"))

    assert abs(heavier.uphill_gravitational_kwh - lighter.uphill_gravitational_kwh * 2) < Decimal(
        "1e-24"
    )


def test_calculation_is_deterministic() -> None:
    elevations = (
        Decimal(100),
        Decimal(110),
        None,
        Decimal(120),
        Decimal(130),
    )

    first = _calculate(elevations)
    second = _calculate(elevations)

    assert first == second


def test_invalid_vehicle_mass_is_rejected() -> None:
    normalized = normalize_terrain_profile(_profile((Decimal(100), Decimal(120))))

    with pytest.raises(TypeError):
        calculate_terrain_gravitational_energy(
            normalized,
            vehicle_mass=None,  # type: ignore[arg-type]
        )


def test_unknown_segments_preserve_original_order() -> None:
    result = _calculate(
        (
            Decimal(100),
            Decimal(110),
            None,
            Decimal(130),
            Decimal(140),
        )
    )

    assert [
        (segment.start_distance_meters, segment.end_distance_meters) for segment in result.segments
    ] == [
        (0, 250),
        (250, 500),
        (500, 750),
        (750, 1000),
    ]

    assert [segment.is_usable for segment in result.segments] == [True, False, False, True]
