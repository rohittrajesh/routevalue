"""Provider-neutral gravitational energy aggregation for normalized terrain."""

from dataclasses import dataclass
from decimal import Decimal

from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    TerrainSegmentStatus,
)
from routevalue.domain.gravitational_energy import gravitational_energy_kwh
from routevalue.domain.units import Meters
from routevalue.domain.vehicle_mass import VehicleMass


@dataclass(frozen=True, slots=True)
class TerrainSegmentEnergy:
    """Mechanical gravitational energy for one route-distance interval."""

    start_distance_meters: Meters
    end_distance_meters: Meters
    gravitational_kwh: Decimal | None

    @property
    def distance_meters(self) -> Meters:
        return self.end_distance_meters - self.start_distance_meters

    @property
    def is_usable(self) -> bool:
        return self.gravitational_kwh is not None


@dataclass(frozen=True, slots=True)
class TerrainEnergyResult:
    """Aggregated mechanical energy with explicit unknown terrain."""

    route_distance_meters: Meters
    segments: tuple[TerrainSegmentEnergy, ...]
    usable_distance_meters: Meters
    unknown_distance_meters: Meters
    coverage: Decimal
    uphill_gravitational_kwh: Decimal
    downhill_gravitational_kwh: Decimal

    @property
    def net_gravitational_kwh(self) -> Decimal:
        """Signed mechanical energy over usable segments only."""

        return self.uphill_gravitational_kwh - self.downhill_gravitational_kwh

    @property
    def is_complete(self) -> bool:
        return self.unknown_distance_meters == 0


def calculate_terrain_gravitational_energy(
    profile: NormalizedTerrainProfile,
    *,
    vehicle_mass: VehicleMass,
) -> TerrainEnergyResult:
    """Calculate mechanical gravitational energy along known route segments.

    Unknown or rejected elevation segments retain their original distances.
    They receive None, never an assumed gravitational energy of zero.

    This function does not calculate vehicle fuel or battery consumption.
    """

    if not isinstance(profile, NormalizedTerrainProfile):
        raise TypeError("profile must be a NormalizedTerrainProfile")

    if not isinstance(vehicle_mass, VehicleMass):
        raise TypeError("vehicle_mass must be a VehicleMass")

    results: list[TerrainSegmentEnergy] = []

    uphill = Decimal(0)
    downhill = Decimal(0)

    for segment in profile.segments:
        energy: Decimal | None = None

        if segment.status is TerrainSegmentStatus.USABLE:
            change = segment.elevation_change_meters

            if change is None:
                raise ValueError("usable terrain segment requires elevation change")

            energy = gravitational_energy_kwh(
                vehicle_mass=vehicle_mass,
                elevation_change_meters=change,
            )

            if energy > 0:
                uphill += energy
            elif energy < 0:
                downhill += -energy

        results.append(
            TerrainSegmentEnergy(
                start_distance_meters=segment.start_distance_meters,
                end_distance_meters=segment.end_distance_meters,
                gravitational_kwh=energy,
            )
        )

    return TerrainEnergyResult(
        route_distance_meters=profile.route_distance_meters,
        segments=tuple(results),
        usable_distance_meters=profile.usable_distance_meters,
        unknown_distance_meters=profile.unknown_distance_meters,
        coverage=profile.coverage,
        uphill_gravitational_kwh=uphill,
        downhill_gravitational_kwh=downhill,
    )
