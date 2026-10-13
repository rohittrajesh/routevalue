"""M7-B1 tests for deterministic terrain normalization."""

from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import (
    ElevationSample,
    GeometryFidelity,
    TerrainProfile,
)
from routevalue.application.terrain_normalization import (
    TERRAIN_ELEVATION_DEADBAND_METERS,
    TERRAIN_MAX_ABSOLUTE_GRADE,
    TerrainSegmentStatus,
    normalize_terrain_profile,
)


def _profile(
    elevations: tuple[Decimal | None, ...],
    *,
    spacing: int = 250,
    fidelity: GeometryFidelity = GeometryFidelity.SIMPLIFIED,
) -> TerrainProfile:
    samples = tuple(
        ElevationSample(
            point=RoutePoint(latitude=32.0, longitude=-117.0),
            distance_meters=index * spacing,
            elevation_meters=elevation,
        )
        for index, elevation in enumerate(elevations)
    )

    return TerrainProfile(
        route_distance_meters=(len(samples) - 1) * spacing,
        samples=samples,
        geometry_fidelity=fidelity,
    )


def test_flat_terrain_has_full_coverage_and_zero_adjustment() -> None:
    profile = _profile((Decimal(100), Decimal(100), Decimal(100)))
    result = normalize_terrain_profile(profile)

    assert result.coverage == Decimal(1)
    assert result.usable_distance_meters == 500
    assert result.unknown_distance_meters == 0
    assert result.elevation_gain_meters == 0
    assert result.elevation_loss_meters == 0
    assert all(segment.grade == 0 for segment in result.segments)


def test_monotonic_uphill_preserves_gain() -> None:
    profile = _profile((Decimal(100), Decimal(110), Decimal(120)))
    result = normalize_terrain_profile(profile)

    assert result.elevation_gain_meters == Decimal(20)
    assert result.elevation_loss_meters == 0
    assert result.coverage == 1

    for segment in result.segments:
        assert segment.grade is not None
        assert segment.grade > 0


def test_monotonic_downhill_preserves_loss() -> None:
    profile = _profile((Decimal(120), Decimal(110), Decimal(100)))
    result = normalize_terrain_profile(profile)

    assert result.elevation_gain_meters == 0
    assert result.elevation_loss_meters == Decimal(20)

    for segment in result.segments:
        assert segment.grade is not None
        assert segment.grade < 0


def test_isolated_elevation_spike_is_removed_by_median_filter() -> None:
    profile = _profile((Decimal(100), Decimal(160), Decimal(100)))
    result = normalize_terrain_profile(profile)

    assert result.coverage == 1
    assert result.elevation_gain_meters == 0
    assert result.elevation_loss_meters == 0
    assert all(segment.grade == 0 for segment in result.segments)


def test_small_elevation_changes_become_flat() -> None:
    profile = _profile((Decimal(100), Decimal(101), Decimal(102)))
    result = normalize_terrain_profile(profile)

    assert TERRAIN_ELEVATION_DEADBAND_METERS == Decimal(2)
    assert result.elevation_gain_meters == 0
    assert result.coverage == 1


def test_missing_middle_elevation_remains_unknown() -> None:
    profile = _profile((Decimal(100), None, Decimal(120)))
    result = normalize_terrain_profile(profile)

    assert result.coverage == 0
    assert result.unknown_distance_meters == 500
    assert all(
        segment.status is TerrainSegmentStatus.MISSING_ELEVATION for segment in result.segments
    )


def test_partial_profile_preserves_known_distance() -> None:
    profile = _profile((Decimal(100), Decimal(110), Decimal(120), None, None))
    result = normalize_terrain_profile(profile)

    assert result.usable_distance_meters == 500
    assert result.unknown_distance_meters == 500
    assert result.coverage == Decimal("0.5")
    assert result.elevation_gain_meters == Decimal(20)


def test_extreme_grade_is_rejected_instead_of_clipped() -> None:
    profile = _profile((Decimal(100), Decimal(200)))
    result = normalize_terrain_profile(profile)

    assert TERRAIN_MAX_ABSOLUTE_GRADE == Decimal("0.35")
    assert result.coverage == 0
    assert result.elevation_gain_meters == 0
    assert result.segments[0].status is TerrainSegmentStatus.EXTREME_GRADE
    assert result.segments[0].elevation_change_meters is None


def test_exact_grade_threshold_remains_usable() -> None:
    profile = _profile((Decimal(100), Decimal("187.5")))
    result = normalize_terrain_profile(profile)

    assert result.coverage == 1
    assert result.segments[0].grade == Decimal("0.35")


def test_terrain_fidelity_is_preserved() -> None:
    profile = _profile(
        (Decimal(100), Decimal(110)),
        fidelity=GeometryFidelity.DETAILED,
    )
    result = normalize_terrain_profile(profile)

    assert result.geometry_fidelity is GeometryFidelity.DETAILED


def test_normalization_is_deterministic_and_nonmutating() -> None:
    profile = _profile((Decimal(100), Decimal(110), None, Decimal(120)))
    original_samples = profile.samples

    first = normalize_terrain_profile(profile)
    second = normalize_terrain_profile(profile)

    assert first == second
    assert profile.samples == original_samples


def test_invalid_filter_configuration_is_rejected() -> None:
    profile = _profile((Decimal(100), Decimal(110)))

    with pytest.raises(ValueError):
        normalize_terrain_profile(profile, elevation_deadband_meters=Decimal(-1))

    with pytest.raises(ValueError):
        normalize_terrain_profile(profile, max_absolute_grade=Decimal(0))

    with pytest.raises(ValueError):
        normalize_terrain_profile(profile, max_absolute_grade=Decimal("NaN"))


def test_no_interpolation_across_missing_observations() -> None:
    profile = _profile((Decimal(100), Decimal(110), None, Decimal(130), Decimal(140)))
    result = normalize_terrain_profile(profile)

    assert result.coverage == Decimal("0.5")
    assert result.elevation_gain_meters == Decimal(20)
    assert result.unknown_distance_meters == 500
