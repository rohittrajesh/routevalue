"""Conservative geometry-fidelity policy for terrain-aware ranking."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from routevalue.application.terrain import GeometryFidelity
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
)


class TerrainGeometryReason(StrEnum):
    """Why terrain geometry may or may not support route ranking."""

    ACCEPTED = "accepted"
    MISSING_PROFILE = "missing_profile"
    UNTRUSTED_GEOMETRY = "untrusted_geometry"


@dataclass(frozen=True, slots=True)
class TerrainGeometryDecision:
    """Trip-wide decision based on declared geometry fidelity."""

    allowed: bool
    reason: TerrainGeometryReason
    blocking_candidate_indices: tuple[int, ...]


def evaluate_trip_terrain_geometry(
    profiles: Sequence[NormalizedTerrainProfile | None],
) -> TerrainGeometryDecision:
    """Require explicitly detailed geometry for every candidate.

    This is a conservative release gate, not a measurement of road
    elevation accuracy.

    Simplified, unknown, or missing geometry prevents trip-wide
    terrain adjustments. The caller can still use M5 baseline energy.
    """

    if not profiles:
        raise ValueError("trip must contain at least one terrain profile")

    missing: list[int] = []
    untrusted: list[int] = []

    for index, profile in enumerate(profiles):
        if profile is None:
            missing.append(index)
            continue

        if not isinstance(profile, NormalizedTerrainProfile):
            raise TypeError("profiles must contain NormalizedTerrainProfile or None")

        if profile.geometry_fidelity is not GeometryFidelity.DETAILED:
            untrusted.append(index)

    blockers = tuple(sorted((*missing, *untrusted)))

    if missing:
        reason = TerrainGeometryReason.MISSING_PROFILE
    elif untrusted:
        reason = TerrainGeometryReason.UNTRUSTED_GEOMETRY
    else:
        reason = TerrainGeometryReason.ACCEPTED

    return TerrainGeometryDecision(
        allowed=not blockers,
        reason=reason,
        blocking_candidate_indices=blockers,
    )
