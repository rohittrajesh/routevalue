"""Prepare route-aligned normalized terrain from acquisition outcomes."""

from collections.abc import Sequence

from routevalue.application.models import ProvidedRoute
from routevalue.application.terrain import TerrainAcquisitionResult
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    normalize_terrain_profile,
)


def prepare_trip_terrain_profiles(
    routes: Sequence[ProvidedRoute],
    acquisitions: Sequence[TerrainAcquisitionResult],
) -> tuple[NormalizedTerrainProfile | None, ...]:
    """Convert ordered acquisition results into normalized route profiles.

    Preserve original candidate indices and missing terrain.

    Malformed alignment is rejected, not silently reassigned. This
    function performs no routing, elevation requests, or energy evaluation.
    """

    if len(routes) != len(acquisitions):
        raise ValueError("route and terrain acquisition counts must match")

    prepared: list[NormalizedTerrainProfile | None] = []

    for index, (provided, acquisition) in enumerate(zip(routes, acquisitions, strict=True)):
        if not isinstance(provided, ProvidedRoute):
            raise TypeError("routes must contain ProvidedRoute")

        if not isinstance(acquisition, TerrainAcquisitionResult):
            raise TypeError("acquisitions must contain TerrainAcquisitionResult")

        if acquisition.route_index != index:
            raise ValueError(f"terrain acquisition route index mismatch at index {index}")

        profile = acquisition.profile

        if profile is None:
            prepared.append(None)
            continue

        if profile.route_distance_meters != provided.route.distance_meters:
            raise ValueError(f"terrain acquisition distance mismatch at index {index}")

        prepared.append(normalize_terrain_profile(profile))

    return tuple(prepared)
