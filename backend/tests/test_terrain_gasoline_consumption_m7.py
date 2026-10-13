"""M7-D2 route-level gasoline terrain consumption tests."""

from decimal import Decimal

import pytest

from routevalue.application.terrain_energy import (
    TerrainEnergyResult,
    TerrainSegmentEnergy,
)
from routevalue.application.terrain_gasoline_consumption import (
    estimate_terrain_gasoline_consumption,
)
from routevalue.domain.energy_consumption import (
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


def _route(distance: int = 160_934) -> RouteCandidate:
    return RouteCandidate(
        distance_meters=distance,
        duration_seconds=3600,
        toll_cost=Decimal(0),
    )


def _vehicle(
    *,
    with_mass: bool = True,
) -> GasolineVehicleSpecification:
    mass = (
        VehicleMass(
            kilograms=Decimal(1500),
            source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        )
        if with_mass
        else None
    )

    return GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=mass,
    )


def _terrain(
    energies: tuple[Decimal | None, ...],
    *,
    route_distance: int = 160_934,
) -> TerrainEnergyResult:
    if not energies:
        raise ValueError("test terrain requires at least one segment")

    segments: list[TerrainSegmentEnergy] = []

    for index, energy in enumerate(energies):
        start = route_distance * index // len(energies)
        end = route_distance * (index + 1) // len(energies)

        segments.append(
            TerrainSegmentEnergy(
                start_distance_meters=start,
                end_distance_meters=end,
                gravitational_kwh=energy,
            )
        )

    usable_distance = sum(
        segment.distance_meters for segment in segments if segment.gravitational_kwh is not None
    )

    uphill = sum(
        (max(Decimal(0), energy) for energy in energies if energy is not None),
        Decimal(0),
    )

    downhill = sum(
        (max(Decimal(0), -energy) for energy in energies if energy is not None),
        Decimal(0),
    )

    return TerrainEnergyResult(
        route_distance_meters=route_distance,
        segments=tuple(segments),
        usable_distance_meters=usable_distance,
        unknown_distance_meters=route_distance - usable_distance,
        coverage=Decimal(usable_distance) / Decimal(route_distance),
        uphill_gravitational_kwh=uphill,
        downhill_gravitational_kwh=downhill,
    )


def _estimate(
    energies: tuple[Decimal | None, ...] | None,
    *,
    vehicle: GasolineVehicleSpecification | None = None,
) -> Decimal:
    route = _route()
    chosen_vehicle = vehicle if vehicle is not None else _vehicle()

    terrain = _terrain(energies) if energies is not None else None

    return estimate_terrain_gasoline_consumption(
        route,
        vehicle=chosen_vehicle,
        terrain=terrain,
    ).gallons


def test_missing_terrain_preserves_exact_m5_baseline() -> None:
    route = _route()
    vehicle = _vehicle()

    expected = estimate_baseline_gasoline_consumption(route, vehicle=vehicle)

    actual = estimate_terrain_gasoline_consumption(route, vehicle=vehicle, terrain=None)

    assert actual == expected


def test_flat_terrain_preserves_exact_m5_baseline() -> None:
    route = _route()
    vehicle = _vehicle()

    expected = estimate_baseline_gasoline_consumption(route, vehicle=vehicle)

    actual = estimate_terrain_gasoline_consumption(
        route,
        vehicle=vehicle,
        terrain=_terrain((Decimal(0), Decimal(0))),
    )

    assert actual == expected


def test_missing_mass_preserves_exact_m5_baseline() -> None:
    route = _route()
    vehicle = _vehicle(with_mass=False)

    baseline = estimate_baseline_gasoline_consumption(route, vehicle=vehicle)

    result = estimate_terrain_gasoline_consumption(
        route,
        vehicle=vehicle,
        terrain=_terrain((Decimal(1), Decimal(-1))),
    )

    assert result == baseline


def test_entirely_unknown_terrain_preserves_baseline() -> None:
    assert _estimate((None, None, None)) == _estimate(None)


def test_uphill_increases_route_consumption() -> None:
    baseline = _estimate(None)
    adjusted = _estimate((Decimal("0.5"), Decimal("0.5")))

    assert adjusted > baseline


def test_downhill_reduces_route_consumption() -> None:
    baseline = _estimate(None)
    adjusted = _estimate((Decimal("-0.5"), Decimal("-0.5")))

    assert Decimal(0) <= adjusted < baseline


def test_mixed_hills_retain_separate_segment_corrections() -> None:
    baseline = _estimate(None)

    adjusted = _estimate((Decimal(1), Decimal(-1)))

    assert abs(adjusted - baseline) < Decimal("1e-24")


def test_excessive_descent_cannot_offset_other_segment_fuel() -> None:
    baseline = _estimate(None)

    result = _estimate((Decimal(1), Decimal(-1000)))

    # First segment consumes its baseline plus uphill fuel.
    # Second segment cannot consume negative gallons.
    assert result > baseline / 2
    assert result >= 0


def test_unknown_segment_keeps_its_baseline_share() -> None:
    baseline = _estimate(None)

    adjusted = _estimate((Decimal("0.8425"), None))

    expected = baseline + Decimal("0.1")

    assert abs(adjusted - expected) < Decimal("1e-24")


def test_zero_distance_without_terrain_preserves_baseline() -> None:
    result = estimate_terrain_gasoline_consumption(
        _route(0),
        vehicle=_vehicle(),
        terrain=None,
    )

    assert result.gallons == 0


def test_mismatched_route_distance_is_rejected() -> None:
    with pytest.raises(ValueError, match="terrain distance"):
        estimate_terrain_gasoline_consumption(
            _route(),
            vehicle=_vehicle(),
            terrain=_terrain((Decimal(1),), route_distance=1000),
        )


def test_segments_must_cover_entire_route() -> None:
    original = _terrain((Decimal(1), Decimal(1)))

    invalid = TerrainEnergyResult(
        route_distance_meters=original.route_distance_meters,
        segments=(
            TerrainSegmentEnergy(
                start_distance_meters=0,
                end_distance_meters=1000,
                gravitational_kwh=Decimal(1),
            ),
        ),
        usable_distance_meters=1000,
        unknown_distance_meters=159_934,
        coverage=Decimal(1000) / Decimal(160_934),
        uphill_gravitational_kwh=Decimal(1),
        downhill_gravitational_kwh=Decimal(0),
    )

    with pytest.raises(ValueError, match="cover the full route"):
        estimate_terrain_gasoline_consumption(_route(), vehicle=_vehicle(), terrain=invalid)


def test_all_segments_are_checked_for_continuity() -> None:
    invalid = TerrainEnergyResult(
        route_distance_meters=1000,
        segments=(
            TerrainSegmentEnergy(0, 400, Decimal(1)),
            TerrainSegmentEnergy(500, 1000, Decimal(1)),
        ),
        usable_distance_meters=900,
        unknown_distance_meters=100,
        coverage=Decimal("0.9"),
        uphill_gravitational_kwh=Decimal(2),
        downhill_gravitational_kwh=Decimal(0),
    )

    with pytest.raises(ValueError, match="continuous and ordered"):
        estimate_terrain_gasoline_consumption(_route(1000), vehicle=_vehicle(), terrain=invalid)


def test_consumption_is_deterministic() -> None:
    energies = (Decimal("0.25"), None, Decimal("-0.1"))

    assert _estimate(energies) == _estimate(energies)
