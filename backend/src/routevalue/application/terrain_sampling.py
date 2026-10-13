"""Deterministic, provider-neutral route geometry sampling for terrain requests."""

from bisect import bisect_right
from dataclasses import dataclass
from math import acos, asin, atan2, cos, degrees, hypot, isfinite, pi, radians, sin, sqrt

from routevalue.application.models import RouteGeometry, RoutePoint
from routevalue.application.terrain import TerrainUnavailableReason
from routevalue.domain.units import Meters

EARTH_MEAN_RADIUS_METERS = 6_371_008.8
DEFAULT_TERRAIN_SPACING_METERS = 250
MAX_TERRAIN_SAMPLES_PER_ROUTE = 256


@dataclass(frozen=True, slots=True)
class TerrainSampleLocation:
    """A requested coordinate paired with an offset along the reported route."""

    point: RoutePoint
    distance_meters: Meters

    def __post_init__(self) -> None:
        if isinstance(self.distance_meters, bool) or not isinstance(self.distance_meters, int):
            raise TypeError("distance_meters must be an integer")
        if self.distance_meters < 0:
            raise ValueError("distance_meters cannot be negative")
        if not isinstance(self.point, RoutePoint):
            raise TypeError("point must be a RoutePoint")


@dataclass(frozen=True, slots=True)
class RouteSamplingResult:
    """Coordinates to query, or a reason that geometry cannot be sampled."""

    locations: tuple[TerrainSampleLocation, ...] = ()
    unavailable_reason: TerrainUnavailableReason | None = None
    geometry_length_meters: float | None = None
    spacing_was_increased: bool = False

    def __post_init__(self) -> None:
        if self.unavailable_reason is None:
            if len(self.locations) < 2:
                raise ValueError("successful route sampling requires at least two locations")
            if self.geometry_length_meters is None or not (
                isfinite(self.geometry_length_meters) and self.geometry_length_meters > 0
            ):
                raise ValueError("successful sampling requires positive geometry length")
            if self.locations[0].distance_meters != 0:
                raise ValueError("route sampling must start at zero")
            if any(
                later.distance_meters <= earlier.distance_meters
                for earlier, later in zip(self.locations, self.locations[1:])
            ):
                raise ValueError("sample offsets must increase strictly")
        elif (
            self.locations or self.geometry_length_meters is not None or self.spacing_was_increased
        ):
            raise ValueError("unavailable sampling cannot include locations or geometry length")


class _UnusableGeometryError(ValueError):
    """Degenerate geometry cannot be interpolated reliably."""


def _distance_meters(start: RoutePoint, end: RoutePoint) -> float:
    """Great-circle length between two geographic coordinates."""

    lat1 = radians(start.latitude)
    lat2 = radians(end.latitude)
    lat_diff = lat2 - lat1
    lon_diff = radians(end.longitude - start.longitude)
    haversine = sin(lat_diff / 2) ** 2 + cos(lat1) * cos(lat2) * sin(lon_diff / 2) ** 2
    return 2 * EARTH_MEAN_RADIUS_METERS * asin(min(1.0, sqrt(max(0.0, haversine))))


def _unit_vector(point: RoutePoint) -> tuple[float, float, float]:
    latitude = radians(point.latitude)
    longitude = radians(point.longitude)
    return (
        cos(latitude) * cos(longitude),
        cos(latitude) * sin(longitude),
        sin(latitude),
    )


def _interpolate_point(start: RoutePoint, end: RoutePoint, fraction: float) -> RoutePoint:
    """Interpolate along the short great-circle arc, including across ±180°."""

    if fraction <= 0:
        return start
    if fraction >= 1:
        return end

    first = _unit_vector(start)
    second = _unit_vector(end)
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(first, second))))
    angle = acos(dot)
    if angle >= pi - 1e-8:
        raise _UnusableGeometryError("antipodal segment has ambiguous interpolation")

    if angle < 1e-8:
        latitude = start.latitude + fraction * (end.latitude - start.latitude)
        longitude_delta = (end.longitude - start.longitude + 180) % 360 - 180
        longitude = (start.longitude + fraction * longitude_delta + 180) % 360 - 180
        return RoutePoint(latitude=latitude, longitude=longitude)

    weight_first = sin((1 - fraction) * angle) / sin(angle)
    weight_second = sin(fraction * angle) / sin(angle)
    x, y, z = (weight_first * first[i] + weight_second * second[i] for i in range(3))
    return RoutePoint(latitude=degrees(atan2(z, hypot(x, y))), longitude=degrees(atan2(y, x)))


def _usable_geometry(
    geometry: RouteGeometry,
) -> tuple[tuple[RoutePoint, ...], tuple[float, ...]]:
    """Drop repeated vertices while tracking cumulative surface distance."""

    points: list[RoutePoint] = [geometry.points[0]]
    cumulative: list[float] = [0.0]

    for point in geometry.points[1:]:
        if not isfinite(point.latitude) or not isfinite(point.longitude):
            raise _UnusableGeometryError("route coordinates must be finite")
        distance = _distance_meters(points[-1], point)
        if not isfinite(distance):
            raise _UnusableGeometryError("route segment distance is nonfinite")
        if distance == 0:
            continue
        if distance >= pi * EARTH_MEAN_RADIUS_METERS - 0.01:
            raise _UnusableGeometryError("antipodal geometry segment")
        points.append(point)
        cumulative.append(cumulative[-1] + distance)

    if len(points) < 2 or not isfinite(cumulative[-1]) or cumulative[-1] <= 0:
        raise _UnusableGeometryError("route geometry has no usable length")
    return tuple(points), tuple(cumulative)


def sample_route_geometry(
    geometry: RouteGeometry | None,
    *,
    route_distance_meters: Meters,
    target_spacing_meters: Meters = DEFAULT_TERRAIN_SPACING_METERS,
    max_samples: int = MAX_TERRAIN_SAMPLES_PER_ROUTE,
) -> RouteSamplingResult:
    """Sample geometry at reported-route offsets with a hard per-route cap.

    Cumulative great-circle distances establish fractions along the shape;
    offsets use the routing provider's authoritative distance. This assumes
    the polyline shape reasonably follows the driven route and does not
    claim road-grade accuracy for simplified geometry.
    """

    if isinstance(target_spacing_meters, bool) or not isinstance(target_spacing_meters, int):
        raise TypeError("target_spacing_meters must be an integer")
    if target_spacing_meters <= 0:
        raise ValueError("target_spacing_meters must be positive")
    if isinstance(max_samples, bool) or not isinstance(max_samples, int):
        raise TypeError("max_samples must be an integer")
    if max_samples < 2 or max_samples > MAX_TERRAIN_SAMPLES_PER_ROUTE:
        raise ValueError("max_samples must be between 2 and 256")

    if geometry is None:
        return RouteSamplingResult(unavailable_reason=TerrainUnavailableReason.MISSING_GEOMETRY)
    if (
        isinstance(route_distance_meters, bool)
        or not isinstance(route_distance_meters, int)
        or route_distance_meters <= 0
    ):
        return RouteSamplingResult(
            unavailable_reason=TerrainUnavailableReason.INVALID_ROUTE_DISTANCE
        )
    if not isinstance(geometry, RouteGeometry):
        return RouteSamplingResult(unavailable_reason=TerrainUnavailableReason.INVALID_GEOMETRY)
    if not all(isfinite(p.latitude) and isfinite(p.longitude) for p in geometry.points):
        return RouteSamplingResult(unavailable_reason=TerrainUnavailableReason.INVALID_GEOMETRY)

    try:
        points, cumulative = _usable_geometry(geometry)
        ideal_segment_count = (
            route_distance_meters + target_spacing_meters - 1
        ) // target_spacing_meters
        segment_count = min(max_samples - 1, max(1, ideal_segment_count))
        sampled: list[TerrainSampleLocation] = []
        for index in range(segment_count + 1):
            offset = index * route_distance_meters // segment_count
            if index == 0:
                point = geometry.points[0]
            elif index == segment_count:
                point = geometry.points[-1]
            else:
                position = (offset / route_distance_meters) * cumulative[-1]
                segment_index = min(bisect_right(cumulative, position) - 1, len(points) - 2)
                start_distance = cumulative[segment_index]
                length = cumulative[segment_index + 1] - start_distance
                fraction = (position - start_distance) / length
                point = _interpolate_point(
                    points[segment_index], points[segment_index + 1], fraction
                )
            sampled.append(TerrainSampleLocation(point=point, distance_meters=offset))
    except _UnusableGeometryError:
        return RouteSamplingResult(unavailable_reason=TerrainUnavailableReason.INVALID_GEOMETRY)

    return RouteSamplingResult(
        locations=tuple(sampled),
        geometry_length_meters=cumulative[-1],
        spacing_was_increased=ideal_segment_count > max_samples - 1,
    )
