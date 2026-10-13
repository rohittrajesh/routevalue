"""M7-E2 tests for route-level terrain-aware BEV consumption."""

from decimal import Decimal

import pytest

from routevalue.application.terrain_electric_consumption import (
    estimate_terrain_electric_consumption,
)
from routevalue.application.terrain_energy import (
    TerrainEnergyResult,
    TerrainSegmentEnergy,
)
from routevalue.domain.energy_consumption import (
    estimate_baseline_electric_consumption,
)
from routevalue.domain.models import (
    ElectricVehicleSpecification,
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
) -> ElectricVehicleSpecification:
    mass = (
        VehicleMass(
            kilograms=Decimal(2000),
            source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        )
        if with_mass
        else None
    )

    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=mass,
    )


def _terrain(
    energies: tuple[Decimal | None, ...],
    *,
    route_distance: int = 160_934,
) -> TerrainEnergyResult:
    if not energies:
        raise ValueError("test terrain requires at least one segment")

    segments = tuple(
        TerrainSegmentEnergy(
            start_distance_meters=route_distance * index // len(energies),
            end_distance_meters=route_distance * (index + 1) // len(energies),
            gravitational_kwh=energy,
        )
        for index, energy in enumerate(energies)
    )

    usable = sum(
        segment.distance_meters for segment in segments if segment.gravitational_kwh is not None
    )

    uphill = sum(
        (energy for energy in energies if energy is not None and energy > 0),
        Decimal(0),
    )
    downhill = sum(
        (-energy for energy in energies if energy is not None and energy < 0),
        Decimal(0),
    )

    return TerrainEnergyResult(
        route_distance_meters=route_distance,
        segments=segments,
        usable_distance_meters=usable,
        unknown_distance_meters=route_distance - usable,
        coverage=Decimal(usable) / Decimal(route_distance),
        uphill_gravitational_kwh=uphill,
        downhill_gravitational_kwh=downhill,
    )


def _estimate(
    energies: tuple[Decimal | None, ...] | None,
    *,
    vehicle: ElectricVehicleSpecification | None = None,
) -> Decimal:
    route = _route()
    selected_vehicle = vehicle if vehicle is not None else _vehicle()

    terrain = _terrain(energies) if energies is not None else None

    return estimate_terrain_electric_consumption(
        route,
        vehicle=selected_vehicle,
        terrain=terrain,
    ).kilowatt_hours


def test_missing_terrain_preserves_exact_m5_baseline() -> None:
    route = _route()
    vehicle = _vehicle()

    assert estimate_terrain_electric_consumption(
        route, vehicle=vehicle, terrain=None
    ) == estimate_baseline_electric_consumption(route, vehicle=vehicle)


def test_flat_terrain_preserves_exact_baseline() -> None:
    assert _estimate((Decimal(0), Decimal(0))) == _estimate(None)


def test_missing_mass_preserves_exact_baseline() -> None:
    vehicle = _vehicle(with_mass=False)
    assert _estimate((Decimal(1), Decimal(-1)), vehicle=vehicle) == _estimate(None, vehicle=vehicle)


def test_entirely_unknown_terrain_preserves_baseline() -> None:
    assert _estimate((None, None, None)) == _estimate(None)


def test_uphill_increases_electric_consumption() -> None:
    baseline = _estimate(None)
    uphill = _estimate((Decimal("0.5"), Decimal("0.5")))

    assert uphill > baseline


def test_downhill_reduces_electric_consumption() -> None:
    baseline = _estimate(None)
    downhill = _estimate((Decimal("-0.5"), Decimal("-0.5")))

    assert Decimal(0) <= downhill < baseline


def test_equal_hills_do_not_cancel_regeneration_losses() -> None:
    baseline = _estimate(None)
    adjusted = _estimate((Decimal(1), Decimal(-1)))

    assert adjusted > baseline


def test_excessive_descent_cannot_generate_negative_consumption() -> None:
    adjusted = _estimate((Decimal(-1000), Decimal(-1000)))

    # Segment clamping and Decimal arithmetic may leave an
    # extremely small positive rounding residual.
    tolerance = Decimal("1e-24")

    assert Decimal(0) <= adjusted < tolerance


def test_descent_cannot_create_credit_against_other_segments() -> None:
    baseline = _estimate(None)
    adjusted = _estimate((Decimal(1), Decimal(-1000)))

    # Uphill half consumes more than its baseline.
    # Downhill half cannot become negative.
    assert adjusted > baseline / 2
    assert adjusted >= 0


def test_unknown_segment_retains_baseline_share() -> None:
    baseline = _estimate(None)
    adjusted = _estimate((Decimal("0.63"), None))

    # 0.63 mechanical kWh / (0.84 * 0.75) = 1 wall kWh.
    assert abs(adjusted - (baseline + Decimal(1))) < Decimal("1e-24")


def test_zero_distance_without_terrain_returns_zero() -> None:
    result = estimate_terrain_electric_consumption(
        _route(0),
        vehicle=_vehicle(),
        terrain=None,
    )
    assert result.kilowatt_hours == 0


def test_mismatched_route_distance_is_rejected() -> None:
    with pytest.raises(ValueError, match="terrain distance"):
        estimate_terrain_electric_consumption(
            _route(),
            vehicle=_vehicle(),
            terrain=_terrain((Decimal(1),), route_distance=1000),
        )


def test_discontinuous_segments_are_rejected() -> None:
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
        estimate_terrain_electric_consumption(_route(1000), vehicle=_vehicle(), terrain=invalid)


def test_inconsistent_aggregate_energy_is_rejected() -> None:
    original = _terrain((Decimal(1), Decimal(-1)))

    invalid = TerrainEnergyResult(
        route_distance_meters=original.route_distance_meters,
        segments=original.segments,
        usable_distance_meters=original.usable_distance_meters,
        unknown_distance_meters=original.unknown_distance_meters,
        coverage=original.coverage,
        uphill_gravitational_kwh=Decimal(999),
        downhill_gravitational_kwh=original.downhill_gravitational_kwh,
    )

    with pytest.raises(ValueError, match="uphill energy"):
        estimate_terrain_electric_consumption(_route(), vehicle=_vehicle(), terrain=invalid)


def test_result_is_deterministic() -> None:
    energies = (Decimal("0.25"), None, Decimal("-0.1"))

    assert _estimate(energies) == _estimate(energies)
