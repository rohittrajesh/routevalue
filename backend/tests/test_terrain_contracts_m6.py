"""M6-B tests for provider-neutral terrain contracts and missingness."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from typing import cast

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import (
    ElevationSample,
    GeometryFidelity,
    GradeSegment,
    TerrainAcquisitionResult,
    TerrainAcquisitionStatus,
    TerrainProfile,
    TerrainUnavailableReason,
)


def _sample(
    distance_meters: int,
    elevation: str | None,
    *,
    resolution: str | None = None,
) -> ElevationSample:
    return ElevationSample(
        point=RoutePoint(latitude=32.88, longitude=-117.23),
        distance_meters=distance_meters,
        elevation_meters=Decimal(elevation) if elevation is not None else None,
        resolution_meters=Decimal(resolution) if resolution is not None else None,
    )


def _profile(*, partial: bool = False) -> TerrainProfile:
    return TerrainProfile(
        route_distance_meters=500,
        samples=(
            _sample(0, "100", resolution="4.5"),
            _sample(250, None if partial else "110"),
            _sample(500, "105"),
        ),
        geometry_fidelity=GeometryFidelity.SIMPLIFIED,
    )


def test_elevation_sample_keeps_point_distance_and_below_sea_level() -> None:
    sample = _sample(250, "-12.25", resolution="5")
    assert sample.point == RoutePoint(latitude=32.88, longitude=-117.23)
    assert sample.distance_meters == 250
    assert sample.elevation_meters == Decimal("-12.25")
    assert sample.resolution_meters == Decimal(5)


def test_missing_elevation_is_not_treated_as_zero() -> None:
    sample = _sample(250, None)
    assert sample.elevation_meters is None
    assert sample.resolution_meters is None


@pytest.mark.parametrize("distance", [-1, True])
def test_sample_rejects_invalid_route_offset(distance: int) -> None:
    with pytest.raises(ValueError, match="nonnegative integer"):
        _sample(distance, "100")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_sample_rejects_nonfinite_elevation(value: str) -> None:
    with pytest.raises(ValueError, match="elevation_meters"):
        _sample(0, value)


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity"])
def test_sample_rejects_invalid_resolution(value: str) -> None:
    with pytest.raises(ValueError, match="resolution_meters must be positive"):
        _sample(0, "100", resolution=value)


def test_sample_rejects_resolution_without_elevation() -> None:
    with pytest.raises(ValueError, match="requires an elevation"):
        _sample(0, None, resolution="10")


def test_sample_rejects_non_point_input() -> None:
    with pytest.raises(ValueError, match="finite geographic coordinates"):
        ElevationSample(
            point=cast(RoutePoint, object()),
            distance_meters=0,
            elevation_meters=Decimal(1),
        )


def test_grade_segments_calculate_signed_rise_over_run() -> None:
    uphill = GradeSegment(start=_sample(0, "100"), end=_sample(250, "110"))
    downhill = GradeSegment(start=_sample(250, "110"), end=_sample(500, "105"))
    assert uphill.distance_meters == 250
    assert uphill.elevation_change_meters == Decimal(10)
    assert uphill.grade == Decimal("0.04")
    assert downhill.elevation_change_meters == Decimal(-5)
    assert downhill.grade == Decimal("-0.02")


def test_grade_is_unknown_when_an_elevation_is_missing() -> None:
    segment = GradeSegment(start=_sample(0, None), end=_sample(250, "100"))
    assert segment.elevation_change_meters is None
    assert segment.grade is None


def test_grade_rejects_nonincreasing_distance() -> None:
    with pytest.raises(ValueError, match="increasing route distance"):
        GradeSegment(start=_sample(250, "100"), end=_sample(250, "110"))


def test_profile_keeps_order_and_complete_grade_segments() -> None:
    profile = _profile()
    assert profile.geometry_fidelity == GeometryFidelity.SIMPLIFIED
    assert profile.is_complete
    assert profile.missing_sample_count == 0
    assert tuple(segment.grade for segment in profile.grade_segments) == (
        Decimal("0.04"),
        Decimal("-0.02"),
    )


def test_partial_profile_keeps_known_samples_and_unknown_grades() -> None:
    profile = _profile(partial=True)
    assert not profile.is_complete
    assert profile.missing_sample_count == 1
    assert tuple(segment.grade for segment in profile.grade_segments) == (None, None)


@pytest.mark.parametrize(
    "route_distance,samples",
    [
        (0, (_sample(0, "100"), _sample(500, "105"))),
        (500, (_sample(0, "100"),)),
        (500, (_sample(1, "100"), _sample(500, "105"))),
        (500, (_sample(0, "100"), _sample(499, "105"))),
        (
            500,
            (_sample(0, "100"), _sample(250, "110"), _sample(250, "105"), _sample(500, "100")),
        ),
        (
            500,
            (_sample(0, "100"), _sample(400, "110"), _sample(250, "105"), _sample(500, "100")),
        ),
    ],
)
def test_profile_rejects_invalid_distance_alignment(
    route_distance: int,
    samples: tuple[ElevationSample, ...],
) -> None:
    with pytest.raises(ValueError):
        TerrainProfile(route_distance_meters=route_distance, samples=samples)


def test_result_distinguishes_complete_partial_and_unavailable() -> None:
    complete = TerrainAcquisitionResult(route_index=0, profile=_profile())
    partial = TerrainAcquisitionResult(route_index=1, profile=_profile(partial=True))
    unavailable = TerrainAcquisitionResult(
        route_index=2,
        unavailable_reason=TerrainUnavailableReason.MISSING_GEOMETRY,
    )
    assert complete.status == TerrainAcquisitionStatus.COMPLETE
    assert partial.status == TerrainAcquisitionStatus.PARTIAL
    assert unavailable.status == TerrainAcquisitionStatus.UNAVAILABLE
    assert unavailable.profile is None


def test_result_preserves_route_index_for_identical_route_candidates() -> None:
    first = TerrainAcquisitionResult(route_index=0, profile=_profile())
    second = TerrainAcquisitionResult(route_index=1, profile=_profile())
    assert first.route_index != second.route_index
    assert first.profile == second.profile


def test_result_rejects_missing_or_conflicting_outcomes() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        TerrainAcquisitionResult(route_index=0)
    with pytest.raises(ValueError, match="exactly one"):
        TerrainAcquisitionResult(
            route_index=0,
            profile=_profile(),
            unavailable_reason=TerrainUnavailableReason.DISABLED,
        )


@pytest.mark.parametrize(
    ("index", "expected_exception"),
    [(-1, ValueError), (True, TypeError)],
)
def test_result_rejects_invalid_route_index(
    index: int, expected_exception: type[Exception]
) -> None:
    with pytest.raises(expected_exception, match="route_index"):
        TerrainAcquisitionResult(
            route_index=index,
            unavailable_reason=TerrainUnavailableReason.MISSING_GEOMETRY,
        )


def test_contracts_are_immutable() -> None:
    sample = _sample(0, "100")
    profile = _profile()
    with pytest.raises(FrozenInstanceError):
        sample.__setattr__("distance_meters", 100)
    with pytest.raises(FrozenInstanceError):
        profile.__setattr__("route_distance_meters", 100)
