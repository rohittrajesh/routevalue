"""Pure normalization of M6 terrain observations for V2 energy modeling."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from routevalue.application.terrain import GeometryFidelity, TerrainProfile
from routevalue.domain.units import Meters

TERRAIN_ELEVATION_DEADBAND_METERS = Decimal(2)
TERRAIN_MAX_ABSOLUTE_GRADE = Decimal("0.35")


class TerrainSegmentStatus(StrEnum):
    """Reason a normalized segment is usable or excluded."""

    USABLE = "usable"
    MISSING_ELEVATION = "missing_elevation"
    EXTREME_GRADE = "extreme_grade"


@dataclass(frozen=True, slots=True)
class NormalizedTerrainSegment:
    """A distance interval with a trusted elevation delta, when available."""

    start_distance_meters: Meters
    end_distance_meters: Meters
    elevation_change_meters: Decimal | None
    status: TerrainSegmentStatus

    def __post_init__(self) -> None:
        if self.start_distance_meters < 0:
            raise ValueError("segment start cannot be negative")
        if self.end_distance_meters <= self.start_distance_meters:
            raise ValueError("segment must have positive distance")
        if self.status is TerrainSegmentStatus.USABLE:
            if self.elevation_change_meters is None:
                raise ValueError("usable segment requires elevation change")
            if not self.elevation_change_meters.is_finite():
                raise ValueError("elevation change must be finite")
        elif self.elevation_change_meters is not None:
            raise ValueError("excluded segment cannot contain an elevation change")

    @property
    def distance_meters(self) -> Meters:
        return self.end_distance_meters - self.start_distance_meters

    @property
    def grade(self) -> Decimal | None:
        if self.elevation_change_meters is None:
            return None
        return self.elevation_change_meters / Decimal(self.distance_meters)


@dataclass(frozen=True, slots=True)
class NormalizedTerrainProfile:
    """Normalized segments and distance-weighted coverage metrics."""

    route_distance_meters: Meters
    segments: tuple[NormalizedTerrainSegment, ...]
    geometry_fidelity: GeometryFidelity

    @property
    def usable_distance_meters(self) -> Meters:
        return sum(
            segment.distance_meters
            for segment in self.segments
            if segment.status is TerrainSegmentStatus.USABLE
        )

    @property
    def unknown_distance_meters(self) -> Meters:
        return self.route_distance_meters - self.usable_distance_meters

    @property
    def coverage(self) -> Decimal:
        return Decimal(self.usable_distance_meters) / Decimal(self.route_distance_meters)

    @property
    def elevation_gain_meters(self) -> Decimal:
        return sum(
            (
                max(Decimal(0), segment.elevation_change_meters)
                for segment in self.segments
                if segment.elevation_change_meters is not None
            ),
            Decimal(0),
        )

    @property
    def elevation_loss_meters(self) -> Decimal:
        return sum(
            (
                max(Decimal(0), -segment.elevation_change_meters)
                for segment in self.segments
                if segment.elevation_change_meters is not None
            ),
            Decimal(0),
        )


def _filtered_elevations(
    profile: TerrainProfile,
) -> tuple[Decimal | None, ...]:
    """Median-filter interior observations only within known runs."""

    original = tuple(sample.elevation_meters for sample in profile.samples)
    filtered = list(original)

    for index in range(1, len(original) - 1):
        window = original[index - 1 : index + 2]
        if all(value is not None for value in window):
            known = sorted(value for value in window if value is not None)
            filtered[index] = known[1]

    return tuple(filtered)


def normalize_terrain_profile(
    profile: TerrainProfile,
    *,
    elevation_deadband_meters: Decimal = TERRAIN_ELEVATION_DEADBAND_METERS,
    max_absolute_grade: Decimal = TERRAIN_MAX_ABSOLUTE_GRADE,
) -> NormalizedTerrainProfile:
    """Convert raw elevation observations into conservative grade segments.

    Missing or rejected segments retain their full distance but cannot
    contribute a gravitational energy correction.
    """

    if not isinstance(profile, TerrainProfile):
        raise TypeError("profile must be a TerrainProfile")

    if not elevation_deadband_meters.is_finite() or elevation_deadband_meters < 0:
        raise ValueError("elevation deadband must be finite and nonnegative")

    if not max_absolute_grade.is_finite() or max_absolute_grade <= 0:
        raise ValueError("maximum absolute grade must be finite and positive")

    elevations = _filtered_elevations(profile)
    segments: list[NormalizedTerrainSegment] = []

    for index in range(len(profile.samples) - 1):
        start = profile.samples[index]
        end = profile.samples[index + 1]
        first = elevations[index]
        second = elevations[index + 1]

        status = TerrainSegmentStatus.USABLE
        change: Decimal | None = None

        if first is None or second is None:
            status = TerrainSegmentStatus.MISSING_ELEVATION
        else:
            raw_change = second - first
            distance = end.distance_meters - start.distance_meters
            raw_grade = raw_change / Decimal(distance)

            if abs(raw_grade) > max_absolute_grade:
                status = TerrainSegmentStatus.EXTREME_GRADE
            elif abs(raw_change) <= elevation_deadband_meters:
                change = Decimal(0)
            else:
                change = raw_change

        segments.append(
            NormalizedTerrainSegment(
                start_distance_meters=start.distance_meters,
                end_distance_meters=end.distance_meters,
                elevation_change_meters=change,
                status=status,
            )
        )

    return NormalizedTerrainProfile(
        route_distance_meters=profile.route_distance_meters,
        segments=tuple(segments),
        geometry_fidelity=profile.geometry_fidelity,
    )
