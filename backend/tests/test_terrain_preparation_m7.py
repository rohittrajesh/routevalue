"""M7-G1 tests for route-aligned terrain preparation."""

from decimal import Decimal

import pytest

from routevalue.application.models import ProvidedRoute, RoutePoint
from routevalue.application.terrain import (
    ElevationSample,
    GeometryFidelity,
    TerrainAcquisitionResult,
    TerrainProfile,
    TerrainUnavailableReason,
)
from routevalue.application.terrain_preparation import (
    prepare_trip_terrain_profiles,
)
from routevalue.domain.models import RouteCandidate


def _routes(
    *distances: int,
) -> tuple[ProvidedRoute, ...]:
    return tuple(
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=distance,
                duration_seconds=600 + index,
                toll_cost=Decimal(0),
            )
        )
        for index, distance in enumerate(distances)
    )


def _acquisition(
    index: int,
    *,
    distance: int = 1000,
    first_elevation: str | None = "100",
    last_elevation: str | None = "120",
) -> TerrainAcquisitionResult:
    return TerrainAcquisitionResult(
        route_index=index,
        profile=TerrainProfile(
            route_distance_meters=distance,
            geometry_fidelity=GeometryFidelity.SIMPLIFIED,
            samples=(
                ElevationSample(
                    point=RoutePoint(32.0, -117.0),
                    distance_meters=0,
                    elevation_meters=(
                        Decimal(first_elevation) if first_elevation is not None else None
                    ),
                ),
                ElevationSample(
                    point=RoutePoint(32.01, -117.01),
                    distance_meters=distance,
                    elevation_meters=(
                        Decimal(last_elevation) if last_elevation is not None else None
                    ),
                ),
            ),
        ),
    )


def _unavailable(index: int) -> TerrainAcquisitionResult:
    return TerrainAcquisitionResult(
        route_index=index,
        unavailable_reason=TerrainUnavailableReason.PROVIDER_UNAVAILABLE,
    )


def test_single_profile_is_normalized() -> None:
    result = prepare_trip_terrain_profiles(
        _routes(1000),
        (_acquisition(0),),
    )

    assert len(result) == 1
    profile = result[0]
    assert profile is not None
    assert profile.route_distance_meters == 1000
    assert profile.coverage == Decimal(1)
    assert len(profile.segments) == 1


def test_unavailable_profile_remains_none() -> None:
    result = prepare_trip_terrain_profiles(
        _routes(1000),
        (_unavailable(0),),
    )

    assert result == (None,)


def test_mixed_outcomes_preserve_candidate_order() -> None:
    result = prepare_trip_terrain_profiles(
        _routes(1000, 1000, 1000),
        (
            _acquisition(0, first_elevation="100"),
            _unavailable(1),
            _acquisition(2, first_elevation="200"),
        ),
    )

    assert len(result) == 3
    assert result[0] is not None
    assert result[1] is None
    assert result[2] is not None
    assert result[0].segments[0].elevation_change_meters == Decimal(20)
    assert result[2].segments[0].elevation_change_meters == Decimal(-80)


def test_identical_distance_routes_cannot_swap_acquisitions() -> None:
    with pytest.raises(ValueError, match="route index mismatch"):
        prepare_trip_terrain_profiles(
            _routes(1000, 1000),
            (_acquisition(1), _acquisition(0)),
        )


def test_missing_acquisition_is_rejected() -> None:
    with pytest.raises(ValueError, match="counts must match"):
        prepare_trip_terrain_profiles(
            _routes(1000, 1000),
            (_acquisition(0),),
        )


def test_extra_acquisition_is_rejected() -> None:
    with pytest.raises(ValueError, match="counts must match"):
        prepare_trip_terrain_profiles(
            _routes(1000),
            (_acquisition(0), _unavailable(1)),
        )


def test_distance_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="distance mismatch"):
        prepare_trip_terrain_profiles(
            _routes(2000),
            (_acquisition(0, distance=1000),),
        )


def test_missing_observations_remain_unknown() -> None:
    result = prepare_trip_terrain_profiles(
        _routes(1000),
        (
            _acquisition(
                0,
                first_elevation="100",
                last_elevation=None,
            ),
        ),
    )

    profile = result[0]
    assert profile is not None
    assert profile.coverage == 0
    assert profile.unknown_distance_meters == 1000


def test_empty_trip_returns_empty_profiles() -> None:
    assert prepare_trip_terrain_profiles((), ()) == ()


def test_preparation_is_deterministic() -> None:
    routes = _routes(1000, 1000)
    acquisitions = (_acquisition(0), _unavailable(1))

    first = prepare_trip_terrain_profiles(routes, acquisitions)
    second = prepare_trip_terrain_profiles(routes, acquisitions)

    assert first == second
