"""M7-H2 tests for authenticated profile-driven terrain evaluation."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from routevalue.application.authenticated_terrain_trip import (
    AuthenticatedTerrainTripService,
)
from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteGeometry,
    RoutePoint,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
)
from routevalue.application.profile_resolution import (
    ProfileResolutionService,
    ResolvedEvaluationProfile,
)
from routevalue.application.profile_trip_evaluation import EnergyInputMismatchError
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.application.terrain import ElevationSample, GeometryFidelity
from routevalue.application.terrain_acquisition import TerrainAcquisitionService
from routevalue.application.terrain_geometry_policy import TerrainGeometryReason
from routevalue.application.terrain_sampling import TerrainSampleLocation
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource

_USER_ID = UserId(value=UUID("00000000-0000-4000-8000-000000000001"))
_VEHICLE_ID = SavedVehicleId(value=UUID("00000000-0000-4000-8000-000000000002"))


class _Routes:
    def __init__(self) -> None:
        self.calls = 0

    def get_routes(self, request: RouteSearchRequest) -> Sequence[ProvidedRoute]:
        self.calls += 1
        return (
            ProvidedRoute(
                route=RouteCandidate(1000, 500, Decimal(0)),
                geometry=RouteGeometry((RoutePoint(32.0, -117.0), RoutePoint(32.01, -117.01))),
            ),
            ProvidedRoute(
                route=RouteCandidate(1000, 600, Decimal(0)),
                geometry=RouteGeometry((RoutePoint(33.0, -117.0), RoutePoint(33.01, -117.01))),
            ),
        )


class _Elevations:
    def __init__(self) -> None:
        self.calls = 0

    def get_elevations(
        self, locations: Sequence[TerrainSampleLocation]
    ) -> tuple[ElevationSample, ...]:
        self.calls += 1
        ascending = locations[0].point.latitude < 32.5

        return tuple(
            ElevationSample(
                point=location.point,
                distance_meters=location.distance_meters,
                elevation_meters=(
                    Decimal(100) + Decimal(location.distance_meters) * Decimal("0.04")
                    if ascending
                    else Decimal(140) - Decimal(location.distance_meters) * Decimal("0.04")
                ),
            )
            for location in locations
        )


def _request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation("Origin", 32.0, -117.0),
        destination=ResolvedLocation("Destination", 33.0, -117.0),
    )


def _mass() -> VehicleMass:
    return VehicleMass(
        kilograms=Decimal(1800),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
    )


def _saved_vehicle(*, electric: bool = False) -> SavedVehicle:
    specification = (
        ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.30"),
            vehicle_mass=_mass(),
        )
        if electric
        else GasolineVehicleSpecification(
            combined_mpg=Decimal(30),
            fuel_grade=GasolineGrade.REGULAR,
            vehicle_mass=_mass(),
        )
    )
    timestamp = datetime(2026, 10, 13, tzinfo=UTC)

    return SavedVehicle(
        id=_VEHICLE_ID,
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Example",
            model="Test",
            configuration="Standard",
            source="test",
            source_id="example-1",
        ),
        specification=specification,
        specification_retrieved_at=timestamp,
        saved_at=timestamp,
    )


def _service(
    *,
    electric: bool = False,
    fidelity: GeometryFidelity | None = None,
    enabled: bool = True,
) -> tuple[AuthenticatedTerrainTripService, _Routes, _Elevations, Mock]:
    routing = _Routes()
    elevations = _Elevations()
    resolver = Mock(spec=ProfileResolutionService)
    resolver.resolve_profile.return_value = ResolvedEvaluationProfile(
        value_of_time_per_hour=Decimal(0),
        saved_vehicle=_saved_vehicle(electric=electric),
    )

    acquisition = (
        TerrainAcquisitionService(
            elevation_provider=elevations,
            enabled=enabled,
            geometry_fidelity=fidelity,
        )
        if fidelity is not None
        else None
    )

    service = AuthenticatedTerrainTripService(
        profile_resolution_service=cast(ProfileResolutionService, resolver),
        route_provider=routing,
        terrain_acquisition_service=acquisition,
    )
    return service, routing, elevations, resolver


def test_default_gasoline_path_does_not_request_elevation() -> None:
    service, routes, elevations, resolver = _service()

    result = service.evaluate_trip(
        _USER_ID,
        _request(),
        fuel_price_per_gallon=Decimal("4.50"),
    )

    assert routes.calls == 1
    assert elevations.calls == 0
    assert not result.evaluation.terrain_energy.terrain_applied
    assert result.geometry_decision.reason is TerrainGeometryReason.MISSING_PROFILE
    assert result.evaluation.trip.decision.eligible_count == 2
    resolver.resolve_profile.assert_called_once_with(_USER_ID, requested_vehicle_id=None)


def test_simplified_geometry_forces_baseline_for_all_routes() -> None:
    service, _, elevations, _ = _service(fidelity=GeometryFidelity.SIMPLIFIED)

    outcome = service.evaluate_trip(_USER_ID, _request(), fuel_price_per_gallon=Decimal("4.50"))

    assert elevations.calls == 2
    assert not outcome.geometry_decision.allowed
    assert outcome.geometry_decision.reason is (TerrainGeometryReason.UNTRUSTED_GEOMETRY)
    assert not outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.evaluation.trip.decision.eligible_count == 2


def test_detailed_geometry_enables_gasoline_terrain() -> None:
    service, _, elevations, _ = _service(fidelity=GeometryFidelity.DETAILED)

    outcome = service.evaluate_trip(_USER_ID, _request(), fuel_price_per_gallon=Decimal("4.50"))

    assert elevations.calls == 2
    assert outcome.geometry_decision.allowed
    assert outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.evaluation.trip.decision.eligible_count == 2


def test_detailed_geometry_enables_electric_terrain() -> None:
    service, _, _, _ = _service(electric=True, fidelity=GeometryFidelity.DETAILED)

    outcome = service.evaluate_trip(
        _USER_ID,
        _request(),
        price_per_kilowatt_hour=Decimal("0.30"),
    )

    assert outcome.geometry_decision.allowed
    assert outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.evaluation.trip.decision.eligible_count == 2


def test_wrong_price_type_rejected_before_routing() -> None:
    service, routing, elevations, _ = _service(electric=True)

    with pytest.raises(EnergyInputMismatchError):
        service.evaluate_trip(
            _USER_ID,
            _request(),
            fuel_price_per_gallon=Decimal("4.50"),
        )

    assert routing.calls == 0
    assert elevations.calls == 0


def test_exactly_one_price_type_required() -> None:
    service, routing, _, _ = _service()

    with pytest.raises(ValueError, match="exactly one"):
        service.evaluate_trip(_USER_ID, _request())

    with pytest.raises(ValueError, match="exactly one"):
        service.evaluate_trip(
            _USER_ID,
            _request(),
            fuel_price_per_gallon=Decimal(4),
            price_per_kilowatt_hour=Decimal("0.2"),
        )

    assert routing.calls == 0


def test_explicit_vehicle_id_is_forwarded_to_owned_lookup() -> None:
    service, _, _, resolver = _service()

    service.evaluate_trip(
        _USER_ID,
        _request(),
        fuel_price_per_gallon=Decimal(4),
        requested_vehicle_id=_VEHICLE_ID,
    )

    resolver.resolve_profile.assert_called_once_with(_USER_ID, requested_vehicle_id=_VEHICLE_ID)


def test_disabled_service_never_calls_elevation() -> None:
    service, _, elevations, _ = _service(
        fidelity=GeometryFidelity.DETAILED,
        enabled=False,
    )

    outcome = service.evaluate_trip(_USER_ID, _request(), fuel_price_per_gallon=Decimal(4))

    assert elevations.calls == 0
    assert not outcome.evaluation.terrain_energy.terrain_applied


def test_repeated_default_evaluation_is_deterministic() -> None:
    service, _, _, _ = _service()

    first = service.evaluate_trip(_USER_ID, _request(), fuel_price_per_gallon=Decimal(4))
    second = service.evaluate_trip(_USER_ID, _request(), fuel_price_per_gallon=Decimal(4))

    assert first == second
