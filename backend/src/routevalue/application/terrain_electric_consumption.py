"""Route-level terrain-aware BEV consumption for RouteValue V2."""

from decimal import Decimal

from routevalue.application.terrain_energy import TerrainEnergyResult
from routevalue.domain.energy_consumption import (
    estimate_baseline_electric_consumption,
)
from routevalue.domain.models import (
    ElectricConsumption,
    ElectricVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.terrain_electric import (
    terrain_adjusted_electric_kwh,
)


def _validate_terrain_for_route(
    route: RouteCandidate,
    terrain: TerrainEnergyResult,
) -> None:
    """Reject inconsistent route-distance and terrain-energy inputs."""

    if terrain.route_distance_meters != route.distance_meters:
        raise ValueError("terrain distance must match route distance")

    if route.distance_meters <= 0:
        raise ValueError("terrain evaluation requires positive route distance")

    if not terrain.segments:
        raise ValueError("terrain must contain route segments")

    current_offset = 0
    usable_distance = 0
    uphill = Decimal(0)
    downhill = Decimal(0)

    for segment in terrain.segments:
        if segment.start_distance_meters != current_offset:
            raise ValueError("terrain segments must be continuous and ordered")

        if segment.end_distance_meters <= segment.start_distance_meters:
            raise ValueError("terrain segments must have positive length")

        if segment.end_distance_meters > route.distance_meters:
            raise ValueError("terrain segment exceeds route distance")

        current_offset = segment.end_distance_meters
        energy = segment.gravitational_kwh

        if energy is not None:
            if not isinstance(energy, Decimal) or not energy.is_finite():
                raise ValueError("terrain energy must be finite Decimal")

            usable_distance += segment.distance_meters

            if energy > 0:
                uphill += energy
            elif energy < 0:
                downhill += -energy

    if current_offset != route.distance_meters:
        raise ValueError("terrain segments must cover the full route")

    if usable_distance != terrain.usable_distance_meters:
        raise ValueError("terrain usable distance is inconsistent")

    if terrain.unknown_distance_meters != route.distance_meters - usable_distance:
        raise ValueError("terrain unknown distance is inconsistent")

    expected_coverage = Decimal(usable_distance) / Decimal(route.distance_meters)

    if abs(terrain.coverage - expected_coverage) > Decimal("1e-24"):
        raise ValueError("terrain coverage is inconsistent")

    if abs(terrain.uphill_gravitational_kwh - uphill) > Decimal("1e-24"):
        raise ValueError("terrain uphill energy is inconsistent")

    if abs(terrain.downhill_gravitational_kwh - downhill) > Decimal("1e-24"):
        raise ValueError("terrain downhill energy is inconsistent")


def estimate_terrain_electric_consumption(
    route: RouteCandidate,
    *,
    vehicle: ElectricVehicleSpecification,
    terrain: TerrainEnergyResult | None,
) -> ElectricConsumption:
    """Combine M5 baseline electricity with bounded terrain corrections.

    Missing terrain or vehicle mass preserves the exact M5 baseline.

    Known uphill segments incur additional electrical consumption.
    Known downhill segments can recover energy through regeneration.
    Unknown segments retain baseline energy consumption.

    The caller must enforce trip-wide terrain comparability before
    using this estimate for route ranking.
    """

    baseline = estimate_baseline_electric_consumption(
        route,
        vehicle=vehicle,
    )

    if terrain is None:
        return baseline

    if not isinstance(terrain, TerrainEnergyResult):
        raise TypeError("terrain must be a TerrainEnergyResult or None")

    _validate_terrain_for_route(route, terrain)

    if vehicle.vehicle_mass is None:
        return baseline

    if all(
        segment.gravitational_kwh is None or segment.gravitational_kwh == 0
        for segment in terrain.segments
    ):
        return baseline

    total_correction = Decimal(0)

    for segment in terrain.segments:
        gravitational_energy = segment.gravitational_kwh

        if gravitational_energy is None or gravitational_energy == 0:
            continue

        segment_baseline = (
            baseline.kilowatt_hours
            * Decimal(segment.distance_meters)
            / Decimal(route.distance_meters)
        )

        segment_adjusted = terrain_adjusted_electric_kwh(
            baseline_kwh=segment_baseline,
            gravitational_kwh=gravitational_energy,
        )

        total_correction += segment_adjusted - segment_baseline

    adjusted_kwh = max(
        Decimal(0),
        baseline.kilowatt_hours + total_correction,
    )

    return ElectricConsumption(
        kilowatt_hours=adjusted_kwh,
    )
