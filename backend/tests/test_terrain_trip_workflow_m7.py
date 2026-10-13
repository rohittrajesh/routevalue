"""M7-G3 tests for optional terrain-aware trip workflow composition."""

from collections.abc import Sequence
from decimal import Decimal

import pytest

from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteGeometry,
    RoutePoint,
    RouteSearchRequest,
)
from routevalue.application.terrain import (
    ElevationSample,
    GeometryFidelity,
    TerrainUnavailableReason,
)
from routevalue.application.terrain_acquisition import (
    TerrainAcquisitionService,
)
from routevalue.application.terrain_ports import (
    ElevationProviderQuotaError,
)
from routevalue.application.terrain_sampling import TerrainSampleLocation
from routevalue.application.terrain_trip_workflow import TerrainTripWorkflow
from routevalue.domain.energy_consumption import (
    estimate_baseline_electric_consumption,
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.models import (
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


class _RouteProvider:
    def __init__(self, routes: tuple[ProvidedRoute, ...]) -> None:
        self.routes = routes
        self.calls = 0

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        self.calls += 1
        return self.routes


class _ElevationProvider:
    def __init__(self, *, quota_failure: bool = False) -> None:
        self.calls = 0
        self.quota_failure = quota_failure

    def get_elevations(
        self,
        locations: Sequence[TerrainSampleLocation],
    ) -> tuple[ElevationSample, ...]:
        self.calls += 1

        if self.quota_failure:
            raise ElevationProviderQuotaError("synthetic quota failure")

        # The first candidate climbs; the second descends.
        uphill = locations[0].point.latitude < 32.5

        return tuple(
            ElevationSample(
                point=location.point,
                distance_meters=location.distance_meters,
                elevation_meters=(
                    Decimal(100) + Decimal(location.distance_meters) * Decimal("0.04")
                    if uphill
                    else Decimal(140) - Decimal(location.distance_meters) * Decimal("0.04")
                ),
            )
            for location in locations
        )


def _request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation(
            display_name="Origin",
            latitude=32.0,
            longitude=-117.0,
        ),
        destination=ResolvedLocation(
            display_name="Destination",
            latitude=32.02,
            longitude=-117.02,
        ),
    )


def _routes(
    *,
    second_has_geometry: bool = True,
) -> tuple[ProvidedRoute, ...]:
    first = ProvidedRoute(
        route=RouteCandidate(1000, 500, Decimal(0)),
        geometry=RouteGeometry(
            (
                RoutePoint(32.0, -117.0),
                RoutePoint(32.01, -117.01),
            )
        ),
    )
    second = ProvidedRoute(
        route=RouteCandidate(1000, 600, Decimal(0)),
        geometry=(
            RouteGeometry(
                (
                    RoutePoint(33.0, -117.0),
                    RoutePoint(33.01, -117.01),
                )
            )
            if second_has_geometry
            else None
        ),
    )

    return first, second


def _mass() -> VehicleMass:
    return VehicleMass(
        kilograms=Decimal(1800),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
    )


def _gas_vehicle() -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=_mass(),
    )


def _electric_vehicle() -> ElectricVehicleSpecification:
    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=_mass(),
    )


def _gas_quote() -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )


def _electric_quote() -> ElectricityPriceQuote:
    return ElectricityPriceQuote(
        price_per_kilowatt_hour=Decimal("0.30"),
    )


def _service(
    provider: _ElevationProvider,
    *,
    enabled: bool,
) -> TerrainAcquisitionService:
    return TerrainAcquisitionService(
        elevation_provider=provider,
        enabled=enabled,
        geometry_fidelity=GeometryFidelity.DETAILED,
    )


def test_default_gasoline_workflow_uses_baseline() -> None:
    routes = _routes()
    routing = _RouteProvider(routes)

    outcome = TerrainTripWorkflow(
        route_provider=routing,
    ).evaluate_gasoline_trip(
        _request(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(20),
    )

    assert routing.calls == 1
    assert not outcome.evaluation.terrain_energy.terrain_applied
    assert all(
        acquisition.unavailable_reason is TerrainUnavailableReason.DISABLED
        for acquisition in outcome.acquisitions
    )

    first = outcome.evaluation.trip.route_evaluations[0]
    assert first.energy_estimate is not None
    assert first.energy_estimate.consumption == (
        estimate_baseline_gasoline_consumption(
            routes[0].route,
            vehicle=_gas_vehicle(),
        )
    )


def test_default_electric_workflow_uses_baseline() -> None:
    routes = _routes()

    outcome = TerrainTripWorkflow(
        route_provider=_RouteProvider(routes),
    ).evaluate_electric_trip(
        _request(),
        vehicle=_electric_vehicle(),
        electricity_price_quote=_electric_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert not outcome.evaluation.terrain_energy.terrain_applied
    first = outcome.evaluation.trip.route_evaluations[0]
    assert first.energy_estimate is not None
    assert first.energy_estimate.consumption == (
        estimate_baseline_electric_consumption(
            routes[0].route,
            vehicle=_electric_vehicle(),
        )
    )


def test_supplied_disabled_service_never_calls_elevation_provider() -> None:
    elevation = _ElevationProvider()

    outcome = TerrainTripWorkflow(
        route_provider=_RouteProvider(_routes()),
        terrain_acquisition_service=_service(elevation, enabled=False),
    ).evaluate_gasoline_trip(
        _request(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert elevation.calls == 0
    assert not outcome.evaluation.terrain_energy.terrain_applied


def test_enabled_gasoline_workflow_applies_terrain() -> None:
    elevation = _ElevationProvider()
    routes = _routes()

    outcome = TerrainTripWorkflow(
        route_provider=_RouteProvider(routes),
        terrain_acquisition_service=_service(elevation, enabled=True),
    ).evaluate_gasoline_trip(
        _request(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert elevation.calls == 2
    assert outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.evaluation.trip.decision.eligible_count == 2

    first, second = outcome.evaluation.trip.route_evaluations
    assert first.energy_estimate is not None
    assert second.energy_estimate is not None

    baseline = estimate_baseline_gasoline_consumption(
        routes[0].route,
        vehicle=_gas_vehicle(),
    )

    assert first.energy_estimate.consumption is not None
    assert second.energy_estimate.consumption is not None
    assert first.energy_estimate.cost > (baseline.gallons * _gas_quote().price_per_gallon)
    assert second.energy_estimate.cost < (baseline.gallons * _gas_quote().price_per_gallon)


def test_enabled_electric_workflow_applies_regeneration() -> None:
    elevation = _ElevationProvider()
    routes = _routes()

    outcome = TerrainTripWorkflow(
        route_provider=_RouteProvider(routes),
        terrain_acquisition_service=_service(elevation, enabled=True),
    ).evaluate_electric_trip(
        _request(),
        vehicle=_electric_vehicle(),
        electricity_price_quote=_electric_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert elevation.calls == 2
    assert outcome.evaluation.terrain_energy.terrain_applied

    first, second = outcome.evaluation.trip.route_evaluations
    assert first.energy_estimate is not None
    assert second.energy_estimate is not None

    baseline = estimate_baseline_electric_consumption(
        routes[0].route,
        vehicle=_electric_vehicle(),
    )

    baseline_cost = baseline.kilowatt_hours * _electric_quote().price_per_kilowatt_hour

    assert first.energy_estimate.cost > baseline_cost
    assert second.energy_estimate.cost < baseline_cost


def test_quota_failure_falls_back_without_retrying_other_routes() -> None:
    elevation = _ElevationProvider(quota_failure=True)

    outcome = TerrainTripWorkflow(
        route_provider=_RouteProvider(_routes()),
        terrain_acquisition_service=_service(elevation, enabled=True),
    ).evaluate_gasoline_trip(
        _request(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert elevation.calls == 1
    assert not outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.evaluation.trip.decision.eligible_count == 2
    assert all(
        acquisition.unavailable_reason is TerrainUnavailableReason.REQUEST_BUDGET_EXCEEDED
        for acquisition in outcome.acquisitions
    )


def test_missing_geometry_forces_shared_baseline() -> None:
    elevation = _ElevationProvider()

    outcome = TerrainTripWorkflow(
        route_provider=_RouteProvider(
            _routes(second_has_geometry=False),
        ),
        terrain_acquisition_service=_service(elevation, enabled=True),
    ).evaluate_electric_trip(
        _request(),
        vehicle=_electric_vehicle(),
        electricity_price_quote=_electric_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert elevation.calls == 1
    assert not outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.evaluation.trip.decision.eligible_count == 2
    assert outcome.acquisitions[1].unavailable_reason is (TerrainUnavailableReason.MISSING_GEOMETRY)


def test_missing_price_keeps_existing_eligibility_behavior() -> None:
    outcome = TerrainTripWorkflow(
        route_provider=_RouteProvider(_routes()),
    ).evaluate_electric_trip(
        _request(),
        vehicle=_electric_vehicle(),
        electricity_price_quote=None,
        value_of_time_per_hour=Decimal(0),
    )

    assert outcome.evaluation.trip.decision.eligible_count == 0
    assert outcome.evaluation.trip.decision.missing_data_present
    assert outcome.evaluation.trip.decision.recommended_route is None


def test_negative_value_of_time_is_rejected_before_routing() -> None:
    routing = _RouteProvider(_routes())

    with pytest.raises(ValueError, match="value_of_time"):
        TerrainTripWorkflow(
            route_provider=routing,
        ).evaluate_gasoline_trip(
            _request(),
            vehicle=_gas_vehicle(),
            fuel_price_quote=_gas_quote(),
            value_of_time_per_hour=Decimal(-1),
        )

    assert routing.calls == 0


def test_workflow_is_deterministic() -> None:
    routing = _RouteProvider(_routes())
    workflow = TerrainTripWorkflow(route_provider=routing)

    first = workflow.evaluate_gasoline_trip(
        _request(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(10),
    )
    second = workflow.evaluate_gasoline_trip(
        _request(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(10),
    )

    assert first == second
    assert routing.calls == 2
