"""Opt-in V2 terrain with explicit process-local or shared quota accounting."""

import os
from collections.abc import Callable, Mapping
from functools import lru_cache

import httpx
from sqlalchemy.engine import Engine

from routevalue.application.terrain import GeometryFidelity
from routevalue.application.terrain_acquisition import TerrainAcquisitionService
from routevalue.infrastructure.elevation.open_topo_data import (
    OpenTopoDataElevationProvider,
)
from routevalue.infrastructure.elevation.postgres_gate import PostgresElevationCallGate
from routevalue.infrastructure.elevation.safety import (
    ElevationCallGate,
    PublicElevationCallGate,
    PublicElevationPolicy,
    terrain_live_enabled,
)

TERRAIN_SINGLE_PROCESS_DEV_ENV = "ROUTEVALUE_TERRAIN_SINGLE_PROCESS_DEV"
TERRAIN_QUOTA_MODE_ENV = "ROUTEVALUE_TERRAIN_QUOTA_MODE"
TERRAIN_TRIP_BUDGET_ENV = "ROUTEVALUE_TERRAIN_REQUESTS_PER_TRIP"


def configured_terrain_policy(environment: Mapping[str, str]) -> PublicElevationPolicy:
    """Allow five or six calls, with six as the live composition default.

    The public endpoint is free; the upstream daily/rate ceilings stay unchanged.
    Reject malformed input rather than silently granting a larger allowance.
    """
    setting = environment.get(TERRAIN_TRIP_BUDGET_ENV, "6")
    if setting not in ("5", "6"):
        raise ValueError(f"{TERRAIN_TRIP_BUDGET_ENV} must be exactly '5' or '6'")
    return PublicElevationPolicy(max_requests_per_trip=int(setting))


@lru_cache(maxsize=1)
def _shared_elevation_gate(policy: PublicElevationPolicy) -> PublicElevationCallGate:
    """Preserve the rolling request budget across local development trips."""
    return PublicElevationCallGate(enabled=True, policy=policy)


def build_optional_terrain_acquisition_service(
    *,
    client: httpx.Client,
    engine_factory: Callable[[], Engine] | None = None,
) -> TerrainAcquisitionService | None:
    """Build guarded acquisition only with explicit live opt-in.

    This composition must be paired with a route provider configured
    for HIGH_QUALITY geometry. A high-quality polyline is not a
    guarantee of accurate road elevation; normalization and coverage
    policies remain responsible for rejecting unsuitable terrain data.
    """
    if not terrain_live_enabled():
        return None

    policy = configured_terrain_policy(os.environ)
    mode = os.getenv(TERRAIN_QUOTA_MODE_ENV, "process")
    gate: ElevationCallGate
    if mode == "postgres":
        if engine_factory is None:
            raise ValueError("shared elevation quota requires a database engine factory")
        gate = PostgresElevationCallGate(engine_factory=engine_factory, policy=policy)
    elif mode != "process":
        raise ValueError(f"{TERRAIN_QUOTA_MODE_ENV} must be 'process' or 'postgres'")
    elif os.getenv(TERRAIN_SINGLE_PROCESS_DEV_ENV) != "1":
        raise ValueError(
            "Live elevation acquisition requires explicit single-process development confirmation."
        )
    else:
        gate = _shared_elevation_gate(policy)

    provider = OpenTopoDataElevationProvider(client=client)

    return TerrainAcquisitionService(
        elevation_provider=gate.new_trip(provider),
        elevation_provider_factory=lambda: gate.new_trip(provider),
        trip_request_budget=gate.policy.max_requests_per_trip,
        enabled=True,
        geometry_fidelity=GeometryFidelity.DETAILED,
    )
