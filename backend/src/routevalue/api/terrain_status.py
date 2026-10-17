"""V2-only, truthful reporting of terrain-energy applicability."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

from routevalue.application.terrain import (
    TerrainAcquisitionResult,
    TerrainAcquisitionStatus,
    TerrainUnavailableReason,
)
from routevalue.application.terrain_applicability import TerrainApplicabilityReason
from routevalue.application.terrain_geometry_policy import (
    TerrainGeometryDecision,
    TerrainGeometryReason,
)
from routevalue.application.terrain_trip_energy import TripTerrainEnergyResult


class V2TerrainFallbackReason(StrEnum):
    """Reasons a trip used the standard energy model."""

    ACQUISITION_DISABLED = "acquisition_disabled"
    ELEVATION_UNAVAILABLE = "elevation_unavailable"
    UNTRUSTED_GEOMETRY = "untrusted_geometry"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    INVALID_ROUTE_DISTANCE = "invalid_route_distance"
    MISSING_VEHICLE_MASS = "missing_vehicle_mass"
    SAFETY_FALLBACK = "safety_fallback"


class V2TerrainStatusResponse(BaseModel):
    """Trip-wide energy mode and per-route terrain availability."""

    terrain_applied: bool
    fallback_reasons: list[V2TerrainFallbackReason]
    route_acquisition_statuses: list[TerrainAcquisitionStatus]
    route_coverage_fractions: list[Decimal | None]


def build_v2_terrain_status(
    *,
    acquisitions: tuple[TerrainAcquisitionResult, ...],
    geometry_decision: TerrainGeometryDecision,
    terrain_energy: TripTerrainEnergyResult,
) -> V2TerrainStatusResponse:
    """Report actual evaluation decisions without inferring terrain use."""

    count = len(acquisitions)

    if count == 0:
        raise ValueError("terrain status requires at least one route")

    if len(terrain_energy.estimates) != count:
        raise ValueError("terrain estimate count must match route count")

    coverages = terrain_energy.applicability.candidate_coverages

    if len(coverages) != count:
        raise ValueError("terrain coverage count must match route count")

    if any(acquisition.route_index != index for index, acquisition in enumerate(acquisitions)):
        raise ValueError("terrain acquisition indices must match route order")

    statuses = [acquisition.status for acquisition in acquisitions]

    if terrain_energy.terrain_applied:
        if (
            not geometry_decision.allowed
            or not terrain_energy.applicability.use_terrain
            or terrain_energy.missing_vehicle_mass
            or any(acquisition.profile is None for acquisition in acquisitions)
        ):
            raise ValueError("inconsistent terrain-applied outcome")

        return V2TerrainStatusResponse(
            terrain_applied=True,
            fallback_reasons=[],
            route_acquisition_statuses=statuses,
            route_coverage_fractions=list(coverages),
        )

    reasons: list[V2TerrainFallbackReason] = []

    all_disabled = all(
        acquisition.unavailable_reason is TerrainUnavailableReason.DISABLED
        for acquisition in acquisitions
    )

    if all_disabled:
        reasons.append(V2TerrainFallbackReason.ACQUISITION_DISABLED)
    elif any(acquisition.profile is None for acquisition in acquisitions):
        reasons.append(V2TerrainFallbackReason.ELEVATION_UNAVAILABLE)

    if geometry_decision.reason is TerrainGeometryReason.UNTRUSTED_GEOMETRY:
        reasons.append(V2TerrainFallbackReason.UNTRUSTED_GEOMETRY)

    if terrain_energy.applicability.reason is TerrainApplicabilityReason.INSUFFICIENT_COVERAGE:
        reasons.append(V2TerrainFallbackReason.INSUFFICIENT_COVERAGE)

    if terrain_energy.applicability.reason is TerrainApplicabilityReason.INVALID_ROUTE_DISTANCE:
        reasons.append(V2TerrainFallbackReason.INVALID_ROUTE_DISTANCE)

    if terrain_energy.missing_vehicle_mass:
        reasons.append(V2TerrainFallbackReason.MISSING_VEHICLE_MASS)

    if not reasons:
        reasons.append(V2TerrainFallbackReason.SAFETY_FALLBACK)

    return V2TerrainStatusResponse(
        terrain_applied=False,
        fallback_reasons=reasons,
        route_acquisition_statuses=statuses,
        route_coverage_fractions=list(coverages),
    )
