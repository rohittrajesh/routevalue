"""M6-C tests for deterministic geometry sampling without external HTTP calls."""

from math import isclose

import pytest

from routevalue.application.models import RouteGeometry, RoutePoint
from routevalue.application.terrain import TerrainUnavailableReason
from routevalue.application.terrain_sampling import (
    DEFAULT_TERRAIN_SPACING_METERS,
    MAX_TERRAIN_SAMPLES_PER_ROUTE,
    RouteSamplingResult,
    TerrainSampleLocation,
    sample_route_geometry,
)


def _line() -> RouteGeometry:
    return RouteGeometry(
        points=(
            RoutePoint(latitude=0.0, longitude=0.0),
            RoutePoint(latitude=0.0, longitude=0.01),
        )
    )


def test_default_sampling_parameters_are_bounded() -> None:
    assert DEFAULT_TERRAIN_SPACING_METERS == 250
    assert MAX_TERRAIN_SAMPLES_PER_ROUTE == 256


def test_10_km_route_has_41_evenly_spaced_offsets_and_original_endpoints() -> None:
    geometry = _line()
    result = sample_route_geometry(geometry, route_distance_meters=10_000)
    assert result.unavailable_reason is None
    assert len(result.locations) == 41
    assert [location.distance_meters for location in result.locations] == list(
        range(0, 10_001, 250)
    )
    assert result.locations[0].point == geometry.points[0]
    assert result.locations[-1].point == geometry.points[-1]
    assert not result.spacing_was_increased
    assert result.geometry_length_meters is not None
    assert 1_100 < result.geometry_length_meters < 1_120


def test_intermediate_point_is_halfway_along_equatorial_segment() -> None:
    result = sample_route_geometry(_line(), route_distance_meters=1_000, target_spacing_meters=500)
    middle = result.locations[1]
    assert middle.distance_meters == 500
    assert isclose(middle.point.latitude, 0.0, abs_tol=1e-9)
    assert isclose(middle.point.longitude, 0.005, abs_tol=1e-7)


def test_geometry_vertices_are_used_by_cumulative_geodesic_position() -> None:
    geometry = RouteGeometry(
        points=(
            RoutePoint(latitude=0.0, longitude=0.0),
            RoutePoint(latitude=0.0, longitude=0.01),
            RoutePoint(latitude=0.01, longitude=0.01),
        )
    )
    result = sample_route_geometry(
        geometry, route_distance_meters=2_000, target_spacing_meters=1_000
    )
    assert len(result.locations) == 3
    assert isclose(result.locations[1].point.latitude, 0.0, abs_tol=1e-7)
    assert isclose(result.locations[1].point.longitude, 0.01, abs_tol=1e-7)


def test_repeated_consecutive_vertices_do_not_cause_division_by_zero() -> None:
    start, end = _line().points
    geometry = RouteGeometry(points=(start, start, end, end))
    result = sample_route_geometry(geometry, route_distance_meters=1_000, target_spacing_meters=500)
    assert len(result.locations) == 3
    assert result.locations[0].point == start
    assert result.locations[-1].point == end
    assert isclose(result.locations[1].point.longitude, 0.005, abs_tol=1e-7)


def test_all_coincident_points_are_unusable() -> None:
    start = _line().points[0]
    geometry = RouteGeometry(points=(start, start))
    result = sample_route_geometry(geometry, route_distance_meters=1_000)
    assert result == RouteSamplingResult(
        unavailable_reason=TerrainUnavailableReason.INVALID_GEOMETRY
    )


def test_antimeridian_interpolation_follows_short_arc() -> None:
    geometry = RouteGeometry(
        points=(
            RoutePoint(latitude=0.0, longitude=179.9),
            RoutePoint(latitude=0.0, longitude=-179.9),
        )
    )
    result = sample_route_geometry(
        geometry, route_distance_meters=2_000, target_spacing_meters=1_000
    )
    midpoint = result.locations[1].point
    assert isclose(midpoint.latitude, 0.0, abs_tol=1e-7)
    assert isclose(abs(midpoint.longitude), 180.0, abs_tol=1e-7)
    assert result.locations[0].point == geometry.points[0]
    assert result.locations[-1].point == geometry.points[-1]


def test_antipodal_geometry_is_explicitly_invalid() -> None:
    geometry = RouteGeometry(
        points=(
            RoutePoint(latitude=0, longitude=0),
            RoutePoint(latitude=0, longitude=180),
        )
    )
    result = sample_route_geometry(geometry, route_distance_meters=10_000)
    assert result.unavailable_reason == TerrainUnavailableReason.INVALID_GEOMETRY


def test_sample_budget_cap_increases_spacing_instead_of_call_count() -> None:
    result = sample_route_geometry(_line(), route_distance_meters=100_000)
    assert len(result.locations) == MAX_TERRAIN_SAMPLES_PER_ROUTE
    assert result.spacing_was_increased
    assert result.locations[0].distance_meters == 0
    assert result.locations[-1].distance_meters == 100_000
    assert all(
        earlier.distance_meters < later.distance_meters
        for earlier, later in zip(result.locations, result.locations[1:])
    )


def test_max_samples_parameter_can_reduce_work() -> None:
    result = sample_route_geometry(_line(), route_distance_meters=1_000, max_samples=3)
    assert tuple(location.distance_meters for location in result.locations) == (0, 500, 1_000)
    assert result.spacing_was_increased


def test_small_distance_never_generates_duplicate_offsets() -> None:
    result = sample_route_geometry(_line(), route_distance_meters=1)
    assert tuple(location.distance_meters for location in result.locations) == (0, 1)


def test_nonmultiple_route_distance_retains_exact_last_offset() -> None:
    result = sample_route_geometry(_line(), route_distance_meters=1_001)
    assert tuple(location.distance_meters for location in result.locations) == (
        0,
        200,
        400,
        600,
        800,
        1_001,
    )


@pytest.mark.parametrize("length", [0, -1, True, 2.5])
def test_invalid_route_distances_are_unavailable(length: float) -> None:
    result = sample_route_geometry(_line(), route_distance_meters=length)  # type: ignore[arg-type]
    assert result == RouteSamplingResult(
        unavailable_reason=TerrainUnavailableReason.INVALID_ROUTE_DISTANCE
    )


def test_none_geometry_is_unavailable() -> None:
    result = sample_route_geometry(None, route_distance_meters=1_000)
    assert result.unavailable_reason == TerrainUnavailableReason.MISSING_GEOMETRY
    assert result.locations == ()


@pytest.mark.parametrize("spacing", [0, -1])
def test_invalid_spacing_is_configuration_error(spacing: int) -> None:
    with pytest.raises(ValueError, match="target_spacing_meters must be positive"):
        sample_route_geometry(_line(), route_distance_meters=1_000, target_spacing_meters=spacing)


@pytest.mark.parametrize("size", [0, 1, 257])
def test_invalid_sample_caps_are_configuration_errors(size: int) -> None:
    with pytest.raises(ValueError, match="max_samples must be between"):
        sample_route_geometry(_line(), route_distance_meters=1_000, max_samples=size)


def test_sampling_is_deterministic_and_does_not_mutate_geometry() -> None:
    geometry = _line()
    original_points = geometry.points
    first = sample_route_geometry(geometry, route_distance_meters=2_500)
    second = sample_route_geometry(geometry, route_distance_meters=2_500)
    assert first == second
    assert geometry.points == original_points


def test_sample_location_rejects_invalid_distances() -> None:
    point = _line().points[0]
    with pytest.raises(ValueError, match="cannot be negative"):
        TerrainSampleLocation(point=point, distance_meters=-1)
    with pytest.raises(TypeError, match="must be an integer"):
        TerrainSampleLocation(point=point, distance_meters=True)


def test_sample_location_rejects_invalid_point() -> None:
    with pytest.raises(TypeError, match="must be a RoutePoint"):
        TerrainSampleLocation(point=None, distance_meters=0)  # type: ignore[arg-type]
