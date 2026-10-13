"""Provider-neutral terrain acquisition contracts for RouteValue V2."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from routevalue.application.models import RoutePoint
from routevalue.domain.units import Meters


class GeometryFidelity(StrEnum):
    """How faithfully available geometry represents the traveled route."""

    UNKNOWN = "unknown"
    SIMPLIFIED = "simplified"
    DETAILED = "detailed"


class TerrainAcquisitionStatus(StrEnum):
    """Availability of terrain observations for one route candidate."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class TerrainUnavailableReason(StrEnum):
    """Provider-independent reason that a route has no terrain profile."""

    DISABLED = "disabled"
    MISSING_GEOMETRY = "missing_geometry"
    INVALID_GEOMETRY = "invalid_geometry"
    INVALID_ROUTE_DISTANCE = "invalid_route_distance"
    SAMPLE_BUDGET_EXCEEDED = "sample_budget_exceeded"
    REQUEST_BUDGET_EXCEEDED = "request_budget_exceeded"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_REJECTED = "provider_rejected"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    NO_ELEVATION_DATA = "no_elevation_data"


@dataclass(frozen=True, slots=True)
class ElevationSample:
    """One route-distance-aligned terrain observation in meters.

    Missing elevation is represented by None, never a guessed zero.
    The resolution describes the source observation, not road-grade accuracy.
    """

    point: RoutePoint
    distance_meters: Meters
    elevation_meters: Decimal | None
    resolution_meters: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.point, RoutePoint) or not (
            isfinite(self.point.latitude) and isfinite(self.point.longitude)
        ):
            raise ValueError("point must have finite geographic coordinates")

        if (
            isinstance(self.distance_meters, bool)
            or not isinstance(self.distance_meters, int)
            or self.distance_meters < 0
        ):
            raise ValueError("distance_meters must be a nonnegative integer")

        if self.elevation_meters is not None and (
            not isinstance(self.elevation_meters, Decimal) or not self.elevation_meters.is_finite()
        ):
            raise ValueError("elevation_meters must be finite when present")

        if self.resolution_meters is not None:
            if (
                not isinstance(self.resolution_meters, Decimal)
                or not self.resolution_meters.is_finite()
                or self.resolution_meters <= 0
            ):
                raise ValueError("resolution_meters must be positive and finite")
            if self.elevation_meters is None:
                raise ValueError("resolution_meters requires an elevation observation")


@dataclass(frozen=True, slots=True)
class GradeSegment:
    """Grade between consecutive observations; rise / horizontal run."""

    start: ElevationSample
    end: ElevationSample

    def __post_init__(self) -> None:
        if self.end.distance_meters <= self.start.distance_meters:
            raise ValueError("grade segment requires increasing route distance")

    @property
    def distance_meters(self) -> Meters:
        return self.end.distance_meters - self.start.distance_meters

    @property
    def elevation_change_meters(self) -> Decimal | None:
        if self.start.elevation_meters is None or self.end.elevation_meters is None:
            return None
        return self.end.elevation_meters - self.start.elevation_meters

    @property
    def grade(self) -> Decimal | None:
        """Signed, dimensionless grade (0.04 means a 4% incline)."""

        change = self.elevation_change_meters
        if change is None:
            return None
        return change / Decimal(self.distance_meters)


@dataclass(frozen=True, slots=True)
class TerrainProfile:
    """Distance-aligned samples for one complete route geometry."""

    route_distance_meters: Meters
    samples: tuple[ElevationSample, ...]
    geometry_fidelity: GeometryFidelity = GeometryFidelity.UNKNOWN

    def __post_init__(self) -> None:
        if (
            isinstance(self.route_distance_meters, bool)
            or not isinstance(self.route_distance_meters, int)
            or self.route_distance_meters <= 0
        ):
            raise ValueError("route_distance_meters must be a positive integer")

        if len(self.samples) < 2:
            raise ValueError("terrain profile requires at least two samples")

        if self.samples[0].distance_meters != 0:
            raise ValueError("terrain profile must begin at distance zero")

        if self.samples[-1].distance_meters != self.route_distance_meters:
            raise ValueError("terrain profile must end at the route distance")

        if any(
            later.distance_meters <= earlier.distance_meters
            for earlier, later in zip(self.samples, self.samples[1:])
        ):
            raise ValueError("terrain sample distances must strictly increase")

        if not isinstance(self.geometry_fidelity, GeometryFidelity):
            raise TypeError("geometry_fidelity must be a GeometryFidelity")

    @property
    def missing_sample_count(self) -> int:
        return sum(sample.elevation_meters is None for sample in self.samples)

    @property
    def is_complete(self) -> bool:
        return self.missing_sample_count == 0

    @property
    def grade_segments(self) -> tuple[GradeSegment, ...]:
        return tuple(
            GradeSegment(start=first, end=second)
            for first, second in zip(self.samples, self.samples[1:])
        )


@dataclass(frozen=True, slots=True)
class TerrainAcquisitionResult:
    """Terrain outcome associated with an original route index, not its value."""

    route_index: int
    profile: TerrainProfile | None = None
    unavailable_reason: TerrainUnavailableReason | None = None

    def __post_init__(self) -> None:
        if isinstance(self.route_index, bool) or not isinstance(self.route_index, int):
            raise TypeError("route_index must be a nonnegative integer")
        if self.route_index < 0:
            raise ValueError("route_index must be a nonnegative integer")
        if (self.profile is None) == (self.unavailable_reason is None):
            raise ValueError("terrain result requires exactly one of profile or unavailable_reason")

    @property
    def status(self) -> TerrainAcquisitionStatus:
        if self.profile is None:
            return TerrainAcquisitionStatus.UNAVAILABLE
        if self.profile.is_complete:
            return TerrainAcquisitionStatus.COMPLETE
        return TerrainAcquisitionStatus.PARTIAL
