"""M7-F1 tests for fair trip-wide terrain applicability."""

from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample, TerrainProfile
from routevalue.application.terrain_applicability import (
    MINIMUM_TERRAIN_COVERAGE,
    TerrainApplicabilityReason,
    evaluate_trip_terrain_applicability,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    normalize_terrain_profile,
)
from routevalue.domain.models import RouteCandidate


def _route(distance: int = 1000) -> RouteCandidate:
    return RouteCandidate(
        distance_meters=distance,
        duration_seconds=600,
        toll_cost=Decimal(0),
    )


def _profile(
    elevations: tuple[str | None, ...],
) -> NormalizedTerrainProfile:
    assert len(elevations) >= 2

    distance = 1000

    return normalize_terrain_profile(
        TerrainProfile(
            route_distance_meters=distance,
            samples=tuple(
                ElevationSample(
                    point=RoutePoint(
                        latitude=32.0,
                        longitude=-117.0,
                    ),
                    distance_meters=distance * index // (len(elevations) - 1),
                    elevation_meters=(Decimal(value) if value is not None else None),
                )
                for index, value in enumerate(elevations)
            ),
        )
    )


def _complete() -> NormalizedTerrainProfile:
    return _profile(("100", "110", "120", "130", "140"))


def _partial() -> NormalizedTerrainProfile:
    # Three usable 250m intervals and one unknown interval: 75%.
    return _profile(("100", "110", "120", "130", None))


def test_threshold_is_explicitly_eighty_percent() -> None:
    assert MINIMUM_TERRAIN_COVERAGE == Decimal("0.80")


def test_all_complete_routes_use_terrain() -> None:
    result = evaluate_trip_terrain_applicability(
        [_route(), _route()],
        [_complete(), _complete()],
    )

    assert result.use_terrain
    assert result.reason is TerrainApplicabilityReason.APPLICABLE
    assert result.candidate_coverages == (Decimal(1), Decimal(1))
    assert result.blocking_candidate_indices == ()


def test_single_complete_route_uses_terrain() -> None:
    result = evaluate_trip_terrain_applicability(
        [_route()],
        [_complete()],
    )

    assert result.use_terrain


def test_one_low_coverage_route_disables_all_terrain() -> None:
    result = evaluate_trip_terrain_applicability(
        [_route(), _route(), _route()],
        [_complete(), _partial(), _complete()],
    )

    assert not result.use_terrain
    assert result.reason is TerrainApplicabilityReason.INSUFFICIENT_COVERAGE
    assert result.blocking_candidate_indices == (1,)
    assert result.candidate_coverages == (
        Decimal(1),
        Decimal("0.75"),
        Decimal(1),
    )


def test_missing_profile_disables_trip_terrain() -> None:
    result = evaluate_trip_terrain_applicability(
        [_route(), _route()],
        [_complete(), None],
    )

    assert not result.use_terrain
    assert result.reason is TerrainApplicabilityReason.MISSING_PROFILE
    assert result.candidate_coverages == (Decimal(1), None)
    assert result.blocking_candidate_indices == (1,)


def test_all_missing_profiles_disable_terrain() -> None:
    result = evaluate_trip_terrain_applicability(
        [_route(), _route()],
        [None, None],
    )

    assert not result.use_terrain
    assert result.blocking_candidate_indices == (0, 1)


def test_multiple_blockers_are_reported_in_order() -> None:
    result = evaluate_trip_terrain_applicability(
        [_route(), _route(), _route()],
        [None, _partial(), None],
    )

    assert not result.use_terrain
    assert result.reason is TerrainApplicabilityReason.MISSING_PROFILE
    assert result.blocking_candidate_indices == (0, 1, 2)


def test_exact_threshold_is_accepted() -> None:
    # Four equal 250m intervals, one unknown -> 75%.
    # A custom threshold equal to observed coverage must pass.
    result = evaluate_trip_terrain_applicability(
        [_route()],
        [_partial()],
        minimum_coverage=Decimal("0.75"),
    )

    assert result.use_terrain
    assert result.minimum_required_coverage == Decimal("0.75")


def test_above_threshold_is_accepted() -> None:
    result = evaluate_trip_terrain_applicability(
        [_route()],
        [_partial()],
        minimum_coverage=Decimal("0.70"),
    )

    assert result.use_terrain


def test_zero_distance_disables_terrain_without_division_error() -> None:
    result = evaluate_trip_terrain_applicability(
        [_route(0), _route()],
        [None, _complete()],
    )

    assert not result.use_terrain
    assert result.reason is TerrainApplicabilityReason.INVALID_ROUTE_DISTANCE
    assert result.blocking_candidate_indices == (0,)
    assert result.candidate_coverages == (None, Decimal(1))


def test_route_and_profile_counts_must_match() -> None:
    with pytest.raises(ValueError, match="same length"):
        evaluate_trip_terrain_applicability(
            [_route(), _route()],
            [_complete()],
        )


def test_mismatched_route_distance_is_rejected() -> None:
    with pytest.raises(ValueError, match="terrain distance"):
        evaluate_trip_terrain_applicability(
            [_route(2000)],
            [_complete()],
        )


def test_empty_trip_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one route"):
        evaluate_trip_terrain_applicability([], [])


@pytest.mark.parametrize(
    "threshold",
    [
        Decimal(0),
        Decimal("-0.1"),
        Decimal("1.01"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_invalid_coverage_threshold_is_rejected(
    threshold: Decimal,
) -> None:
    with pytest.raises(ValueError, match="minimum_coverage"):
        evaluate_trip_terrain_applicability(
            [_route()],
            [_complete()],
            minimum_coverage=threshold,
        )


def test_applicability_is_deterministic() -> None:
    routes = [_route(), _route()]
    profiles = [_complete(), _partial()]

    first = evaluate_trip_terrain_applicability(routes, profiles)
    second = evaluate_trip_terrain_applicability(routes, profiles)

    assert first == second
