"""Opt-in local composition for guarded V2 terrain acquisition."""

import os
from functools import lru_cache

import httpx

from routevalue.application.terrain import GeometryFidelity
from routevalue.application.terrain_acquisition import TerrainAcquisitionService
from routevalue.infrastructure.elevation.open_topo_data import (
    OpenTopoDataElevationProvider,
)
from routevalue.infrastructure.elevation.safety import (
    PublicElevationCallGate,
    terrain_live_enabled,
)

TERRAIN_SINGLE_PROCESS_DEV_ENV = "ROUTEVALUE_TERRAIN_SINGLE_PROCESS_DEV"


@lru_cache(maxsize=1)
def _shared_elevation_gate() -> PublicElevationCallGate:
    """Preserve the rolling request budget across local development trips."""
    return PublicElevationCallGate(enabled=True)


def build_optional_terrain_acquisition_service(
    *,
    client: httpx.Client,
) -> TerrainAcquisitionService | None:
    """Build guarded acquisition only with explicit development opt-in.

    This composition must be paired with a route provider configured
    for HIGH_QUALITY geometry. A high-quality polyline is not a
    guarantee of accurate road elevation; normalization and coverage
    policies remain responsible for rejecting unsuitable terrain data.
    """
    if not terrain_live_enabled():
        return None

    if os.getenv(TERRAIN_SINGLE_PROCESS_DEV_ENV) != "1":
        raise ValueError(
            "Live elevation acquisition requires explicit single-process development confirmation."
        )

    provider = OpenTopoDataElevationProvider(client=client)
    guarded_provider = _shared_elevation_gate().new_trip(provider)

    return TerrainAcquisitionService(
        elevation_provider=guarded_provider,
        enabled=True,
        geometry_fidelity=GeometryFidelity.DETAILED,
    )
