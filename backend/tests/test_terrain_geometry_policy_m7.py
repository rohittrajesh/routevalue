"""M7-H1 tests for conservative terrain geometry gating."""

from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import (
    ElevationSample,
    GeometryFidelity,
    TerrainProfile,
)
from routevalue.application.terrain_geometry_policy import (
    TerrainGeometryReason,
    evaluate_trip_terrain_geometry,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    normalize_terrain_profile,
)


def _profile(
    fidelity: GeometryFidelity,
) -> NormalizedTerrainProfile:
    terrain = TerrainProfile(
        route_distance_meters=1000,
        geometry_fidelity=fidelity,
        samples=(
            ElevationSample(
                point=RoutePoint(32.0, -117.0),
                distance_meters=0,
                elevation_meters=Decimal(100),
            ),
            ElevationSample(
                point=RoutePoint(32.01, -117.01),
                distance_meters=1000,
                elevation_meters=Decimal(120),
            ),
        ),
    )
    return normalize_terrain_profile(terrain)


def test_all_detailed_profiles_are_accepted() -> None:
    result = evaluate_trip_terrain_geometry(
        (
            _profile(GeometryFidelity.DETAILED),
            _profile(GeometryFidelity.DETAILED),
        )
    )

    assert result.allowed
    assert result.reason is TerrainGeometryReason.ACCEPTED
    assert result.blocking_candidate_indices == ()


def test_single_detailed_profile_is_accepted() -> None:
    result = evaluate_trip_terrain_geometry((_profile(GeometryFidelity.DETAILED),))

    assert result.allowed


@pytest.mark.parametrize(
    "fidelity",
    [
        GeometryFidelity.SIMPLIFIED,
        GeometryFidelity.UNKNOWN,
    ],
)
def test_untrusted_geometry_blocks_terrain(
    fidelity: GeometryFidelity,
) -> None:
    result = evaluate_trip_terrain_geometry((_profile(fidelity),))

    assert not result.allowed
    assert result.reason is TerrainGeometryReason.UNTRUSTED_GEOMETRY
    assert result.blocking_candidate_indices == (0,)


def test_one_simplified_profile_blocks_entire_trip() -> None:
    result = evaluate_trip_terrain_geometry(
        (
            _profile(GeometryFidelity.DETAILED),
            _profile(GeometryFidelity.SIMPLIFIED),
            _profile(GeometryFidelity.DETAILED),
        )
    )

    assert not result.allowed
    assert result.blocking_candidate_indices == (1,)


def test_missing_profile_blocks_entire_trip() -> None:
    result = evaluate_trip_terrain_geometry(
        (
            _profile(GeometryFidelity.DETAILED),
            None,
        )
    )

    assert not result.allowed
    assert result.reason is TerrainGeometryReason.MISSING_PROFILE
    assert result.blocking_candidate_indices == (1,)


def test_multiple_blockers_preserve_candidate_indices() -> None:
    result = evaluate_trip_terrain_geometry(
        (
            None,
            _profile(GeometryFidelity.SIMPLIFIED),
            _profile(GeometryFidelity.DETAILED),
            _profile(GeometryFidelity.UNKNOWN),
        )
    )

    assert not result.allowed
    assert result.reason is TerrainGeometryReason.MISSING_PROFILE
    assert result.blocking_candidate_indices == (0, 1, 3)


def test_complete_coverage_does_not_override_simplified_fidelity() -> None:
    profile = _profile(GeometryFidelity.SIMPLIFIED)

    assert profile.coverage == Decimal(1)

    result = evaluate_trip_terrain_geometry((profile,))

    assert not result.allowed


def test_different_elevations_do_not_change_geometry_decision() -> None:
    original = _profile(GeometryFidelity.DETAILED)

    altered = normalize_terrain_profile(
        TerrainProfile(
            route_distance_meters=1000,
            geometry_fidelity=GeometryFidelity.DETAILED,
            samples=(
                ElevationSample(
                    point=RoutePoint(32.0, -117.0),
                    distance_meters=0,
                    elevation_meters=Decimal(100),
                ),
                ElevationSample(
                    point=RoutePoint(32.01, -117.01),
                    distance_meters=1000,
                    elevation_meters=Decimal(200),
                ),
            ),
        )
    )

    assert evaluate_trip_terrain_geometry((original,)) == (
        evaluate_trip_terrain_geometry((altered,))
    )


def test_empty_trip_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        evaluate_trip_terrain_geometry(())


def test_geometry_decision_is_deterministic() -> None:
    profiles = (
        _profile(GeometryFidelity.DETAILED),
        _profile(GeometryFidelity.SIMPLIFIED),
    )

    assert evaluate_trip_terrain_geometry(profiles) == (evaluate_trip_terrain_geometry(profiles))
