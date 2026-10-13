"""M7-F2 tests for fair multi-route gasoline and BEV estimates."""

from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample, TerrainProfile
from routevalue.application.terrain_applicability import (
    TerrainApplicabilityReason,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    normalize_terrain_profile,
)
from routevalue.application.terrain_trip_energy import (
    evaluate_trip_electric_energy,
    evaluate_trip_gasoline_energy,
)
from routevalue.domain.electric_energy import estimate_electric_energy
from routevalue.domain.energy_consumption import (
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.models import (
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    GasolineConsumption,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


def _routes() -> tuple[RouteCandidate, ...]:
    return (
        RouteCandidate(1000, 600, Decimal(0)),
        RouteCandidate(1000, 700, Decimal(2)),
        RouteCandidate(1000, 800, Decimal(5)),
    )


def _profile(
    elevations: tuple[str | None, ...],
) -> NormalizedTerrainProfile:
    distance = 1000

    return normalize_terrain_profile(
        TerrainProfile(
            route_distance_meters=distance,
            samples=tuple(
                ElevationSample(
                    point=RoutePoint(latitude=32.0, longitude=-117.0),
                    distance_meters=distance * index // (len(elevations) - 1),
                    elevation_meters=(Decimal(value) if value is not None else None),
                )
                for index, value in enumerate(elevations)
            ),
        )
    )


def _uphill() -> NormalizedTerrainProfile:
    return _profile(("100", "110", "120", "130", "140"))


def _downhill() -> NormalizedTerrainProfile:
    return _profile(("140", "130", "120", "110", "100"))


def _low_coverage() -> NormalizedTerrainProfile:
    return _profile(("100", "110", "120", "130", None))


def _mass() -> VehicleMass:
    return VehicleMass(
        kilograms=Decimal(1800),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
    )


def _gas_vehicle(*, mass: bool = True) -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=_mass() if mass else None,
    )


def _ev_vehicle(*, mass: bool = True) -> ElectricVehicleSpecification:
    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=_mass() if mass else None,
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


def test_gasoline_all_good_profiles_apply_terrain() -> None:
    result = evaluate_trip_gasoline_energy(
        _routes(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(_uphill(), _downhill(), _uphill()),
    )

    assert result.applicability.use_terrain
    assert result.terrain_applied
    assert not result.missing_vehicle_mass
    assert len(result.estimates) == 3

    baseline = estimate_baseline_gasoline_consumption(
        _routes()[0],
        vehicle=_gas_vehicle(),
    )

    first = result.estimates[0]
    assert first is not None
    assert isinstance(first.consumption, GasolineConsumption)
    assert first.consumption.gallons > baseline.gallons


def test_electric_all_good_profiles_apply_terrain() -> None:
    result = evaluate_trip_electric_energy(
        _routes(),
        vehicle=_ev_vehicle(),
        electricity_price_quote=_electric_quote(),
        terrain_profiles=(_uphill(), _downhill(), _uphill()),
    )

    assert result.terrain_applied
    assert result.applicability.use_terrain
    assert all(estimate is not None for estimate in result.estimates)

    first = result.estimates[0]
    assert first is not None
    assert (
        first.cost
        > estimate_electric_energy(
            _routes()[0],
            vehicle=_ev_vehicle(),
            electricity_price_quote=_electric_quote(),
        ).cost
    )


def test_gasoline_low_coverage_forces_all_baselines() -> None:
    routes = _routes()
    vehicle = _gas_vehicle()
    quote = _gas_quote()

    result = evaluate_trip_gasoline_energy(
        routes,
        vehicle=vehicle,
        fuel_price_quote=quote,
        terrain_profiles=(_uphill(), _low_coverage(), _downhill()),
    )

    assert not result.terrain_applied
    assert result.used_baseline_for_all_routes
    assert result.applicability.reason is (TerrainApplicabilityReason.INSUFFICIENT_COVERAGE)
    assert result.applicability.blocking_candidate_indices == (1,)

    for route, estimate in zip(routes, result.estimates, strict=True):
        assert estimate is not None
        baseline = estimate_baseline_gasoline_consumption(route, vehicle=vehicle)
        assert estimate.consumption == baseline
        assert estimate.cost == baseline.gallons * quote.price_per_gallon


def test_electric_low_coverage_forces_all_baselines() -> None:
    routes = _routes()
    vehicle = _ev_vehicle()
    quote = _electric_quote()

    result = evaluate_trip_electric_energy(
        routes,
        vehicle=vehicle,
        electricity_price_quote=quote,
        terrain_profiles=(_uphill(), _low_coverage(), _downhill()),
    )

    assert not result.terrain_applied

    for route, estimate in zip(routes, result.estimates, strict=True):
        assert estimate == estimate_electric_energy(
            route, vehicle=vehicle, electricity_price_quote=quote
        )


def test_gasoline_missing_profile_forces_all_baselines() -> None:
    result = evaluate_trip_gasoline_energy(
        _routes(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(_uphill(), None, _downhill()),
    )

    assert not result.terrain_applied
    assert result.applicability.reason is (TerrainApplicabilityReason.MISSING_PROFILE)
    assert result.applicability.blocking_candidate_indices == (1,)


def test_electric_missing_profile_forces_all_baselines() -> None:
    result = evaluate_trip_electric_energy(
        _routes(),
        vehicle=_ev_vehicle(),
        electricity_price_quote=_electric_quote(),
        terrain_profiles=(_uphill(), None, _downhill()),
    )

    assert not result.terrain_applied
    assert result.applicability.blocking_candidate_indices == (1,)


def test_gasoline_missing_mass_forces_all_baselines() -> None:
    routes = _routes()
    vehicle = _gas_vehicle(mass=False)
    quote = _gas_quote()

    result = evaluate_trip_gasoline_energy(
        routes,
        vehicle=vehicle,
        fuel_price_quote=quote,
        terrain_profiles=(_uphill(), _downhill(), _uphill()),
    )

    assert result.applicability.use_terrain
    assert not result.terrain_applied
    assert result.missing_vehicle_mass

    for route, estimate in zip(routes, result.estimates, strict=True):
        assert estimate is not None
        baseline = estimate_baseline_gasoline_consumption(route, vehicle=vehicle)
        assert estimate.consumption == baseline


def test_electric_missing_mass_forces_all_baselines() -> None:
    routes = _routes()
    vehicle = _ev_vehicle(mass=False)
    quote = _electric_quote()

    result = evaluate_trip_electric_energy(
        routes,
        vehicle=vehicle,
        electricity_price_quote=quote,
        terrain_profiles=(_uphill(), _downhill(), _uphill()),
    )

    assert result.applicability.use_terrain
    assert not result.terrain_applied
    assert result.missing_vehicle_mass

    for route, estimate in zip(routes, result.estimates, strict=True):
        assert estimate == estimate_electric_energy(
            route, vehicle=vehicle, electricity_price_quote=quote
        )


def test_missing_gasoline_price_preserves_none_estimates() -> None:
    result = evaluate_trip_gasoline_energy(
        _routes(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=None,
        terrain_profiles=(_uphill(), _downhill(), _uphill()),
    )

    assert result.terrain_applied
    assert result.estimates == (None, None, None)


def test_missing_electricity_price_preserves_none_estimates() -> None:
    result = evaluate_trip_electric_energy(
        _routes(),
        vehicle=_ev_vehicle(),
        electricity_price_quote=None,
        terrain_profiles=(_uphill(), _downhill(), _uphill()),
    )

    assert result.terrain_applied
    assert result.estimates == (None, None, None)


@pytest.mark.parametrize("kind", ["gasoline", "electric"])
def test_mismatched_profile_counts_rejected(kind: str) -> None:
    if kind == "gasoline":
        with pytest.raises(ValueError, match="same length"):
            evaluate_trip_gasoline_energy(
                _routes(),
                vehicle=_gas_vehicle(),
                fuel_price_quote=_gas_quote(),
                terrain_profiles=(_uphill(),),
            )
    else:
        with pytest.raises(ValueError, match="same length"):
            evaluate_trip_electric_energy(
                _routes(),
                vehicle=_ev_vehicle(),
                electricity_price_quote=_electric_quote(),
                terrain_profiles=(_uphill(),),
            )


def test_result_determinism_for_gasoline() -> None:
    routes = _routes()
    profiles = (_uphill(), _downhill(), _uphill())

    first = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=profiles,
    )
    second = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=profiles,
    )

    assert first == second


def test_result_determinism_for_electricity() -> None:
    routes = _routes()
    profiles = (_uphill(), _downhill(), _uphill())

    first = evaluate_trip_electric_energy(
        routes,
        vehicle=_ev_vehicle(),
        electricity_price_quote=_electric_quote(),
        terrain_profiles=profiles,
    )
    second = evaluate_trip_electric_energy(
        routes,
        vehicle=_ev_vehicle(),
        electricity_price_quote=_electric_quote(),
        terrain_profiles=profiles,
    )

    assert first == second
