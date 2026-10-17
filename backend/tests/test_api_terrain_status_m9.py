"""M9-E2-A tests for truthful V2 terrain-status reporting."""

from decimal import Decimal

import pytest

from routevalue.api.terrain_status import (
    V2TerrainFallbackReason,
    build_v2_terrain_status,
)
from routevalue.application.models import RoutePoint
from routevalue.application.terrain import (
    ElevationSample,
    GeometryFidelity,
    TerrainAcquisitionResult,
    TerrainAcquisitionStatus,
    TerrainProfile,
    TerrainUnavailableReason,
)
from routevalue.application.terrain_applicability import (
    TerrainApplicabilityReason,
    TerrainApplicabilityResult,
)
from routevalue.application.terrain_geometry_policy import (
    TerrainGeometryDecision,
    TerrainGeometryReason,
)
from routevalue.application.terrain_trip_energy import TripTerrainEnergyResult


def _energy(
    *,
    applied: bool = False,
    missing_mass: bool = False,
    reason: TerrainApplicabilityReason = TerrainApplicabilityReason.MISSING_PROFILE,
    coverage: Decimal | None = None,
) -> TripTerrainEnergyResult:
    return TripTerrainEnergyResult(
        estimates=(None,),
        applicability=TerrainApplicabilityResult(
            use_terrain=reason is TerrainApplicabilityReason.APPLICABLE,
            reason=reason,
            minimum_required_coverage=Decimal("0.80"),
            candidate_coverages=(coverage,),
            blocking_candidate_indices=(
                () if reason is TerrainApplicabilityReason.APPLICABLE else (0,)
            ),
        ),
        terrain_applied=applied,
        missing_vehicle_mass=missing_mass,
    )


def _geometry(
    *,
    allowed: bool = False,
    reason: TerrainGeometryReason = TerrainGeometryReason.MISSING_PROFILE,
) -> TerrainGeometryDecision:
    return TerrainGeometryDecision(
        allowed=allowed,
        reason=reason,
        blocking_candidate_indices=() if allowed else (0,),
    )


def _profile() -> TerrainProfile:
    return TerrainProfile(
        route_distance_meters=1000,
        samples=(
            ElevationSample(
                point=RoutePoint(latitude=32.0, longitude=-117.0),
                distance_meters=0,
                elevation_meters=Decimal(10),
            ),
            ElevationSample(
                point=RoutePoint(latitude=32.01, longitude=-117.01),
                distance_meters=1000,
                elevation_meters=Decimal(20),
            ),
        ),
        geometry_fidelity=GeometryFidelity.DETAILED,
    )


def test_disabled_acquisition_is_reported_as_baseline() -> None:
    report = build_v2_terrain_status(
        acquisitions=(
            TerrainAcquisitionResult(
                route_index=0,
                unavailable_reason=TerrainUnavailableReason.DISABLED,
            ),
        ),
        geometry_decision=_geometry(),
        terrain_energy=_energy(),
    )

    assert report.terrain_applied is False
    assert report.fallback_reasons == [V2TerrainFallbackReason.ACQUISITION_DISABLED]
    assert report.route_acquisition_statuses == [TerrainAcquisitionStatus.UNAVAILABLE]
    assert report.route_coverage_fractions == [None]


def test_missing_mass_is_reported_even_with_complete_elevation() -> None:
    report = build_v2_terrain_status(
        acquisitions=(
            TerrainAcquisitionResult(
                route_index=0,
                profile=_profile(),
            ),
        ),
        geometry_decision=_geometry(
            allowed=True,
            reason=TerrainGeometryReason.ACCEPTED,
        ),
        terrain_energy=_energy(
            missing_mass=True,
            reason=TerrainApplicabilityReason.APPLICABLE,
            coverage=Decimal(1),
        ),
    )

    assert report.terrain_applied is False
    assert report.fallback_reasons == [V2TerrainFallbackReason.MISSING_VEHICLE_MASS]
    assert report.route_acquisition_statuses == [TerrainAcquisitionStatus.COMPLETE]


def test_untrusted_geometry_never_claims_terrain_was_applied() -> None:
    report = build_v2_terrain_status(
        acquisitions=(
            TerrainAcquisitionResult(
                route_index=0,
                profile=_profile(),
            ),
        ),
        geometry_decision=_geometry(
            reason=TerrainGeometryReason.UNTRUSTED_GEOMETRY,
        ),
        terrain_energy=_energy(),
    )

    assert report.terrain_applied is False
    assert V2TerrainFallbackReason.UNTRUSTED_GEOMETRY in (report.fallback_reasons)


def test_successful_terrain_application_has_no_fallback_reasons() -> None:
    report = build_v2_terrain_status(
        acquisitions=(
            TerrainAcquisitionResult(
                route_index=0,
                profile=_profile(),
            ),
        ),
        geometry_decision=_geometry(
            allowed=True,
            reason=TerrainGeometryReason.ACCEPTED,
        ),
        terrain_energy=_energy(
            applied=True,
            reason=TerrainApplicabilityReason.APPLICABLE,
            coverage=Decimal(1),
        ),
    )

    assert report.terrain_applied is True
    assert report.fallback_reasons == []
    assert report.route_coverage_fractions == [Decimal(1)]


def test_inconsistent_applied_status_is_rejected() -> None:
    with pytest.raises(ValueError, match="inconsistent terrain-applied"):
        build_v2_terrain_status(
            acquisitions=(
                TerrainAcquisitionResult(
                    route_index=0,
                    unavailable_reason=TerrainUnavailableReason.DISABLED,
                ),
            ),
            geometry_decision=_geometry(),
            terrain_energy=_energy(
                applied=True,
                reason=TerrainApplicabilityReason.APPLICABLE,
                coverage=Decimal(1),
            ),
        )


def test_mismatched_route_counts_are_rejected() -> None:
    with pytest.raises(ValueError, match="estimate count"):
        build_v2_terrain_status(
            acquisitions=(
                TerrainAcquisitionResult(
                    route_index=0,
                    unavailable_reason=TerrainUnavailableReason.DISABLED,
                ),
                TerrainAcquisitionResult(
                    route_index=1,
                    unavailable_reason=TerrainUnavailableReason.DISABLED,
                ),
            ),
            geometry_decision=_geometry(),
            terrain_energy=_energy(),
        )
