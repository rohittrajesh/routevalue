"""Route-level terrain-aware gasoline consumption for RouteValue V2."""

from decimal import Decimal

from routevalue.application.terrain_energy import TerrainEnergyResult
from routevalue.domain.energy_consumption import (
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.models import (
    GasolineConsumption,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.terrain_gasoline import (
    terrain_adjusted_gasoline_gallons,
)


def _validate_terrain_for_route(
    route: RouteCandidate,
    terrain: TerrainEnergyResult,
) -> None:
    """Reject terrain energy that does not describe the requested route."""

    if terrain.route_distance_meters != route.distance_meters:
        raise ValueError("terrain distance must match route distance")

    if not terrain.segments:
        raise ValueError("terrain must contain route segments")

    current_offset = 0
    usable_distance = 0

    for segment in terrain.segments:
        if segment.start_distance_meters != current_offset:
            raise ValueError("terrain segments must be continuous and ordered")

        if segment.end_distance_meters <= segment.start_distance_meters:
            raise ValueError("terrain segments must have positive length")

        if segment.end_distance_meters > route.distance_meters:
            raise ValueError("terrain segment exceeds route distance")

        current_offset = segment.end_distance_meters

        if segment.gravitational_kwh is not None:
            usable_distance += segment.distance_meters

    if current_offset != route.distance_meters:
        raise ValueError("terrain segments must cover the full route")

    if usable_distance != terrain.usable_distance_meters:
        raise ValueError("terrain usable distance is inconsistent")

    if terrain.unknown_distance_meters != route.distance_meters - usable_distance:
        raise ValueError("terrain unknown distance is inconsistent")

    expected_coverage = Decimal(usable_distance) / Decimal(route.distance_meters)

    if terrain.coverage != expected_coverage:
        raise ValueError("terrain coverage is inconsistent")


def estimate_terrain_gasoline_consumption(
    route: RouteCandidate,
    *,
    vehicle: GasolineVehicleSpecification,
    terrain: TerrainEnergyResult | None,
) -> GasolineConsumption:
    """Combine M5 baseline gasoline with bounded terrain corrections.

    None terrain or missing vehicle mass preserves the exact M5 baseline.

    Unknown terrain intervals contribute no gravitational correction.
    Downhill fuel reduction is limited to the baseline of each segment.

    The caller is responsible for the trip-wide terrain applicability
    policy before using this estimate for route comparison.
    """

    baseline = estimate_baseline_gasoline_consumption(
        route,
        vehicle=vehicle,
    )

    if terrain is None or vehicle.vehicle_mass is None:
        return baseline

    if not isinstance(terrain, TerrainEnergyResult):
        raise TypeError("terrain must be a TerrainEnergyResult or None")

    _validate_terrain_for_route(route, terrain)

    # Do not introduce rounding changes when terrain contributes no energy.
    if all(
        segment.gravitational_kwh is None or segment.gravitational_kwh == 0
        for segment in terrain.segments
    ):
        return baseline

    total_correction = Decimal(0)

    for segment in terrain.segments:
        energy = segment.gravitational_kwh

        if energy is None or energy == 0:
            continue

        segment_baseline = (
            baseline.gallons * Decimal(segment.distance_meters) / Decimal(route.distance_meters)
        )

        segment_adjusted = terrain_adjusted_gasoline_gallons(
            baseline_gallons=segment_baseline,
            gravitational_kwh=energy,
        )

        total_correction += segment_adjusted - segment_baseline

    adjusted_gallons = max(
        Decimal(0),
        baseline.gallons + total_correction,
    )

    return GasolineConsumption(
        gallons=adjusted_gallons,
    )
