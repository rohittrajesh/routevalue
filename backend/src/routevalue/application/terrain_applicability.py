"""Trip-wide terrain applicability policy for RouteValue V2."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
)
from routevalue.domain.models import RouteCandidate

MINIMUM_TERRAIN_COVERAGE = Decimal("0.80")


class TerrainApplicabilityReason(StrEnum):
    """Reason for the trip-wide choice of energy-estimation policy."""

    APPLICABLE = "applicable"
    MISSING_PROFILE = "missing_profile"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    INVALID_ROUTE_DISTANCE = "invalid_route_distance"


@dataclass(frozen=True, slots=True)
class TerrainApplicabilityResult:
    """One policy decision shared by every candidate in a trip."""

    use_terrain: bool
    reason: TerrainApplicabilityReason
    minimum_required_coverage: Decimal
    candidate_coverages: tuple[Decimal | None, ...]
    blocking_candidate_indices: tuple[int, ...]


def evaluate_trip_terrain_applicability(
    routes: Sequence[RouteCandidate],
    terrain_profiles: Sequence[NormalizedTerrainProfile | None],
    *,
    minimum_coverage: Decimal = MINIMUM_TERRAIN_COVERAGE,
) -> TerrainApplicabilityResult:
    """Decide whether terrain correction can be used for an entire trip."""

    if not isinstance(minimum_coverage, Decimal):
        raise TypeError("minimum_coverage must be a Decimal")

    if not minimum_coverage.is_finite() or minimum_coverage <= 0 or minimum_coverage > 1:
        raise ValueError("minimum_coverage must be finite and in (0, 1]")

    if not routes:
        raise ValueError("trip must contain at least one route")

    if len(routes) != len(terrain_profiles):
        raise ValueError("routes and terrain_profiles must have the same length")

    coverages: list[Decimal | None] = []
    missing_indices: list[int] = []
    low_coverage_indices: list[int] = []
    invalid_distance_indices: list[int] = []

    for index, (route, profile) in enumerate(zip(routes, terrain_profiles, strict=True)):
        if route.distance_meters <= 0:
            coverages.append(None)
            invalid_distance_indices.append(index)
            continue

        if profile is None:
            coverages.append(None)
            missing_indices.append(index)
            continue

        if not isinstance(profile, NormalizedTerrainProfile):
            raise TypeError("terrain profiles must be NormalizedTerrainProfile or None")

        if profile.route_distance_meters != route.distance_meters:
            raise ValueError(f"terrain distance must match route distance at index {index}")

        # Validate the actual segment geometry, not only computed totals.
        current_offset = 0

        for segment in profile.segments:
            if segment.start_distance_meters != current_offset:
                raise ValueError(f"inconsistent terrain distance coverage at index {index}")

            if segment.end_distance_meters <= segment.start_distance_meters:
                raise ValueError(f"inconsistent terrain distance coverage at index {index}")

            if segment.end_distance_meters > route.distance_meters:
                raise ValueError(f"inconsistent terrain distance coverage at index {index}")

            current_offset = segment.end_distance_meters

        if current_offset != route.distance_meters:
            raise ValueError(f"inconsistent terrain distance coverage at index {index}")

        usable = profile.usable_distance_meters
        unknown = profile.unknown_distance_meters

        if usable < 0 or unknown < 0 or usable + unknown != route.distance_meters:
            raise ValueError(f"inconsistent terrain distance coverage at index {index}")

        actual_coverage = Decimal(usable) / Decimal(route.distance_meters)

        if not profile.coverage.is_finite() or abs(profile.coverage - actual_coverage) > Decimal(
            "1e-24"
        ):
            raise ValueError(f"inconsistent terrain coverage at index {index}")

        coverages.append(actual_coverage)

        if actual_coverage < minimum_coverage:
            low_coverage_indices.append(index)

    if invalid_distance_indices:
        reason = TerrainApplicabilityReason.INVALID_ROUTE_DISTANCE
    elif missing_indices:
        reason = TerrainApplicabilityReason.MISSING_PROFILE
    elif low_coverage_indices:
        reason = TerrainApplicabilityReason.INSUFFICIENT_COVERAGE
    else:
        reason = TerrainApplicabilityReason.APPLICABLE

    blocking = tuple(
        sorted(
            (
                *invalid_distance_indices,
                *missing_indices,
                *low_coverage_indices,
            )
        )
    )

    return TerrainApplicabilityResult(
        use_terrain=not blocking,
        reason=reason,
        minimum_required_coverage=minimum_coverage,
        candidate_coverages=tuple(coverages),
        blocking_candidate_indices=blocking,
    )
