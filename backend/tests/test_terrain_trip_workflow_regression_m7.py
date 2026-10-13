"""M7-G4 fault-isolation regression tests for the V2 terrain workflow."""

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
    ElevationProviderResponseError,
    ElevationProviderUnavailableError,
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
    IneligibilityReason,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


class _Routes:
    def __init__(self, routes: tuple[ProvidedRoute, ...]) -> None:
        self.routes = routes
        self.calls = 0

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        self.calls += 1
        return self.routes


class _Elevations:
    """Deterministic synthetic provider with per-route fault injection."""

    def __init__(
        self,
        *,
        failures: dict[int, str] | None = None,
    ) -> None:
        self.failures = failures or {}
        self.calls: list[int] = []

    def get_elevations(
        self,
        locations: Sequence[TerrainSampleLocation],
    ) -> tuple[ElevationSample, ...]:
        # Route identity is encoded in the latitude of its first point.
        route_index = round(locations[0].point.latitude - 32)
        self.calls.append(route_index)

        failure = self.failures.get(route_index)

        if failure == "unavailable":
            raise ElevationProviderUnavailableError("synthetic outage")

        if failure == "quota":
            raise ElevationProviderQuotaError("synthetic quota exhaustion")

        if failure == "response":
            raise ElevationProviderResponseError("synthetic invalid response")

        if failure == "wrong_order":
            observations = self._observations(route_index, locations)
            return tuple(reversed(observations))

        return self._observations(
            route_index,
            locations,
            missing_last=failure == "partial",
        )

    @staticmethod
    def _observations(
        route_index: int,
        locations: Sequence[TerrainSampleLocation],
        *,
        missing_last: bool = False,
    ) -> tuple[ElevationSample, ...]:
        return tuple(
            ElevationSample(
                point=location.point,
                distance_meters=location.distance_meters,
                elevation_meters=(
                    None
                    if missing_last and index == len(locations) - 1
                    else (
                        Decimal(100) + Decimal(location.distance_meters) * Decimal("0.04")
                        if route_index % 2 == 0
                        else Decimal(200) - Decimal(location.distance_meters) * Decimal("0.04")
                    )
                ),
            )
            for index, location in enumerate(locations)
        )


def _request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation("Origin", 32.0, -117.0),
        destination=ResolvedLocation("Destination", 32.1, -117.1),
    )


def _routes(
    count: int = 3,
    *,
    distance: int = 1000,
    missing_toll_index: int | None = None,
) -> tuple[ProvidedRoute, ...]:
    return tuple(
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=distance,
                duration_seconds=600 + 60 * index,
                toll_cost=(None if index == missing_toll_index else Decimal(index)),
            ),
            geometry=RouteGeometry(
                points=(
                    RoutePoint(32.0 + index, -117.0),
                    RoutePoint(32.01 + index, -117.01),
                )
            ),
        )
        for index in range(count)
    )


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


def _ev_vehicle() -> ElectricVehicleSpecification:
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


def _ev_quote() -> ElectricityPriceQuote:
    return ElectricityPriceQuote(
        price_per_kilowatt_hour=Decimal("0.30"),
    )


def _workflow(
    routes: tuple[ProvidedRoute, ...],
    elevations: _Elevations,
    *,
    enabled: bool = True,
) -> TerrainTripWorkflow:
    return TerrainTripWorkflow(
        route_provider=_Routes(routes),
        terrain_acquisition_service=TerrainAcquisitionService(
            elevation_provider=elevations,
            enabled=enabled,
            geometry_fidelity=GeometryFidelity.DETAILED,
        ),
    )


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        ("unavailable", TerrainUnavailableReason.PROVIDER_UNAVAILABLE),
        ("response", TerrainUnavailableReason.INVALID_PROVIDER_RESPONSE),
        ("wrong_order", TerrainUnavailableReason.INVALID_PROVIDER_RESPONSE),
    ],
)
def test_provider_failure_forces_shared_gasoline_baseline(
    failure: str,
    reason: TerrainUnavailableReason,
) -> None:
    routes = _routes()
    elevations = _Elevations(failures={1: failure})

    outcome = _workflow(
        routes,
        elevations,
    ).evaluate_gasoline_trip(
        _request(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(15),
    )

    assert not outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.acquisitions[1].unavailable_reason is reason
    assert outcome.evaluation.trip.decision.eligible_count == 3
    assert not outcome.evaluation.trip.decision.missing_data_present

    for provided, evaluated in zip(
        routes,
        outcome.evaluation.trip.route_evaluations,
        strict=True,
    ):
        baseline = estimate_baseline_gasoline_consumption(
            provided.route,
            vehicle=_gas_vehicle(),
        )

        assert evaluated.energy_estimate is not None
        assert evaluated.energy_estimate.consumption == baseline
        assert evaluated.energy_estimate.cost == (baseline.gallons * _gas_quote().price_per_gallon)


def test_partial_profile_below_threshold_forces_electric_baseline() -> None:
    routes = _routes()
    elevations = _Elevations(failures={1: "partial"})

    outcome = _workflow(
        routes,
        elevations,
    ).evaluate_electric_trip(
        _request(),
        vehicle=_ev_vehicle(),
        electricity_price_quote=_ev_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert not outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.evaluation.terrain_energy.applicability.candidate_coverages == (
        Decimal(1),
        Decimal("0.75"),
        Decimal(1),
    )

    for provided, evaluated in zip(
        routes,
        outcome.evaluation.trip.route_evaluations,
        strict=True,
    ):
        assert evaluated.energy_estimate is not None
        assert evaluated.energy_estimate.consumption == (
            estimate_baseline_electric_consumption(
                provided.route,
                vehicle=_ev_vehicle(),
            )
        )


def test_exact_eighty_percent_allows_terrain() -> None:
    # 1,250m creates five 250m intervals.
    # One missing final observation leaves 4/5 usable = 80%.
    routes = _routes(2, distance=1250)
    elevations = _Elevations(failures={1: "partial"})

    outcome = _workflow(
        routes,
        elevations,
    ).evaluate_electric_trip(
        _request(),
        vehicle=_ev_vehicle(),
        electricity_price_quote=_ev_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert outcome.evaluation.terrain_energy.applicability.candidate_coverages == (
        Decimal(1),
        Decimal("0.8"),
    )
    assert outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.evaluation.trip.decision.eligible_count == 2


def test_quota_exhaustion_stops_later_elevation_requests() -> None:
    routes = _routes(3)
    elevations = _Elevations(failures={1: "quota"})

    outcome = _workflow(
        routes,
        elevations,
    ).evaluate_electric_trip(
        _request(),
        vehicle=_ev_vehicle(),
        electricity_price_quote=_ev_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert elevations.calls == [0, 1]
    assert outcome.acquisitions[1].unavailable_reason is (
        TerrainUnavailableReason.REQUEST_BUDGET_EXCEEDED
    )
    assert outcome.acquisitions[2].unavailable_reason is (
        TerrainUnavailableReason.REQUEST_BUDGET_EXCEEDED
    )
    assert not outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.evaluation.trip.decision.eligible_count == 3


def test_disabled_terrain_never_invokes_elevation_provider() -> None:
    routes = _routes(3)
    elevations = _Elevations()

    outcome = _workflow(
        routes,
        elevations,
        enabled=False,
    ).evaluate_gasoline_trip(
        _request(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert elevations.calls == []
    assert not outcome.evaluation.terrain_energy.terrain_applied
    assert all(
        item.unavailable_reason is TerrainUnavailableReason.DISABLED
        for item in outcome.acquisitions
    )


def test_missing_price_does_not_become_zero_cost() -> None:
    routes = _routes(2)

    outcome = _workflow(
        routes,
        _Elevations(),
    ).evaluate_electric_trip(
        _request(),
        vehicle=_ev_vehicle(),
        electricity_price_quote=None,
        value_of_time_per_hour=Decimal(0),
    )

    assert outcome.evaluation.trip.decision.eligible_count == 0
    assert outcome.evaluation.trip.decision.missing_data_present
    assert all(
        evaluated.energy_estimate is None
        and evaluated.eligibility.reason is IneligibilityReason.MISSING_ENERGY_ESTIMATE
        for evaluated in outcome.evaluation.trip.route_evaluations
    )


def test_missing_toll_does_not_disable_terrain() -> None:
    routes = _routes(2, missing_toll_index=0)

    outcome = _workflow(
        routes,
        _Elevations(),
    ).evaluate_gasoline_trip(
        _request(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert outcome.evaluation.terrain_energy.terrain_applied
    assert outcome.evaluation.trip.decision.eligible_count == 1
    assert outcome.evaluation.trip.decision.missing_data_present
    assert outcome.evaluation.trip.route_evaluations[0].eligibility.reason is (
        IneligibilityReason.MISSING_TOLL_COST
    )


def test_repeated_faulted_workflows_are_deterministic() -> None:
    routes = _routes(3)

    def run_once() -> object:
        return _workflow(
            routes,
            _Elevations(failures={1: "unavailable"}),
        ).evaluate_gasoline_trip(
            _request(),
            vehicle=_gas_vehicle(),
            fuel_price_quote=_gas_quote(),
            value_of_time_per_hour=Decimal(20),
        )

    assert run_once() == run_once()
