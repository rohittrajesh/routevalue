"""M7-F4 safety and regression tests for trip-wide terrain fairness."""

from dataclasses import replace
from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample, TerrainProfile
from routevalue.application.terrain_applicability import (
    TerrainApplicabilityReason,
    evaluate_trip_terrain_applicability,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    normalize_terrain_profile,
)
from routevalue.application.terrain_trip_energy import (
    evaluate_trip_electric_energy,
    evaluate_trip_gasoline_energy,
)
from routevalue.domain.decision_engine import decide_route
from routevalue.domain.electric_energy import estimate_electric_energy
from routevalue.domain.energy_consumption import (
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.models import (
    DecisionCandidate,
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


def _routes() -> tuple[RouteCandidate, ...]:
    return (
        RouteCandidate(1000, 500, Decimal(0)),
        RouteCandidate(1000, 600, Decimal(2)),
        RouteCandidate(1000, 700, Decimal(4)),
    )


def _profile(
    elevations: tuple[str | None, ...],
) -> NormalizedTerrainProfile:
    assert len(elevations) >= 2

    distance = 1000

    return normalize_terrain_profile(
        TerrainProfile(
            route_distance_meters=distance,
            samples=tuple(
                ElevationSample(
                    point=RoutePoint(
                        latitude=32.0,
                        longitude=-117.0,
                    ),
                    distance_meters=(distance * index // (len(elevations) - 1)),
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


def _gas_vehicle(
    *,
    known_mass: bool = True,
) -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=_mass() if known_mass else None,
    )


def _electric_vehicle(
    *,
    known_mass: bool = True,
) -> ElectricVehicleSpecification:
    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=_mass() if known_mass else None,
    )


def _gas_quote() -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )


def _electric_quote() -> ElectricityPriceQuote:
    return ElectricityPriceQuote(price_per_kilowatt_hour=Decimal("0.30"))


def test_all_routes_receive_baseline_after_single_low_coverage() -> None:
    routes = _routes()
    vehicle = _gas_vehicle()
    quote = _gas_quote()

    result = evaluate_trip_gasoline_energy(
        routes,
        vehicle=vehicle,
        fuel_price_quote=quote,
        terrain_profiles=(
            _uphill(),
            _low_coverage(),
            _downhill(),
        ),
    )

    assert not result.terrain_applied
    assert result.used_baseline_for_all_routes
    assert result.applicability.blocking_candidate_indices == (1,)

    for route, estimate in zip(routes, result.estimates, strict=True):
        assert estimate is not None
        baseline = estimate_baseline_gasoline_consumption(
            route,
            vehicle=vehicle,
        )
        assert estimate.consumption == baseline
        assert estimate.cost == baseline.gallons * quote.price_per_gallon


def test_all_electric_routes_fallback_after_missing_profile() -> None:
    routes = _routes()
    vehicle = _electric_vehicle()
    quote = _electric_quote()

    result = evaluate_trip_electric_energy(
        routes,
        vehicle=vehicle,
        electricity_price_quote=quote,
        terrain_profiles=(
            _uphill(),
            None,
            _downhill(),
        ),
    )

    assert not result.terrain_applied
    assert result.applicability.reason is (TerrainApplicabilityReason.MISSING_PROFILE)

    for route, estimate in zip(routes, result.estimates, strict=True):
        assert estimate == estimate_electric_energy(
            route,
            vehicle=vehicle,
            electricity_price_quote=quote,
        )


def test_missing_gasoline_mass_disables_all_terrain() -> None:
    routes = _routes()
    vehicle = _gas_vehicle(known_mass=False)

    result = evaluate_trip_gasoline_energy(
        routes,
        vehicle=vehicle,
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(
            _uphill(),
            _downhill(),
            _uphill(),
        ),
    )

    assert result.applicability.use_terrain
    assert result.missing_vehicle_mass
    assert not result.terrain_applied

    for route, estimate in zip(routes, result.estimates, strict=True):
        assert estimate is not None
        assert estimate.consumption == estimate_baseline_gasoline_consumption(
            route,
            vehicle=vehicle,
        )


def test_missing_electric_mass_disables_all_terrain() -> None:
    routes = _routes()
    vehicle = _electric_vehicle(known_mass=False)
    quote = _electric_quote()

    result = evaluate_trip_electric_energy(
        routes,
        vehicle=vehicle,
        electricity_price_quote=quote,
        terrain_profiles=(
            _uphill(),
            _downhill(),
            _uphill(),
        ),
    )

    assert result.applicability.use_terrain
    assert result.missing_vehicle_mass
    assert not result.terrain_applied

    for route, estimate in zip(routes, result.estimates, strict=True):
        assert estimate == estimate_electric_energy(
            route,
            vehicle=vehicle,
            electricity_price_quote=quote,
        )


def test_multiple_blockers_preserve_original_candidate_indices() -> None:
    result = evaluate_trip_terrain_applicability(
        _routes(),
        (
            None,
            _uphill(),
            _low_coverage(),
        ),
    )

    assert not result.use_terrain
    assert result.blocking_candidate_indices == (0, 2)
    assert result.candidate_coverages == (
        None,
        Decimal(1),
        Decimal("0.75"),
    )


def test_zero_distance_candidate_blocks_trip_terrain() -> None:
    routes = (
        RouteCandidate(0, 0, Decimal(0)),
        _routes()[1],
    )

    result = evaluate_trip_terrain_applicability(
        routes,
        (None, _downhill()),
    )

    assert not result.use_terrain
    assert result.reason is (TerrainApplicabilityReason.INVALID_ROUTE_DISTANCE)
    assert result.blocking_candidate_indices == (0,)


def test_corrupted_coverage_metadata_is_rejected() -> None:
    profile = _uphill()

    # Introduce inconsistent geometry by changing the declared route
    # distance without changing the original segment endpoints.
    corrupted = replace(
        profile,
        route_distance_meters=2000,
    )

    with pytest.raises(ValueError, match="terrain distance"):
        evaluate_trip_terrain_applicability(
            (_routes()[0],),
            (corrupted,),
        )


def test_corrupted_distance_metadata_is_rejected() -> None:
    profile = _uphill()

    # Modify an underlying segment instead of a computed property.
    first_segment = profile.segments[0]

    corrupted_segment = replace(
        first_segment,
        end_distance_meters=100,
    )

    corrupted = replace(
        profile,
        segments=(
            corrupted_segment,
            *profile.segments[1:],
        ),
    )

    # This changes the total usable distance while retaining the
    # original declared route distance.
    with pytest.raises(ValueError, match="distance coverage"):
        evaluate_trip_terrain_applicability(
            (_routes()[0],),
            (corrupted,),
        )


def test_mismatched_profile_distance_is_rejected() -> None:
    routes = (RouteCandidate(2000, 500, Decimal(0)),)

    with pytest.raises(ValueError, match="terrain distance"):
        evaluate_trip_terrain_applicability(
            routes,
            (_uphill(),),
        )


def test_missing_gasoline_price_is_not_zero_cost() -> None:
    result = evaluate_trip_gasoline_energy(
        _routes(),
        vehicle=_gas_vehicle(),
        fuel_price_quote=None,
        terrain_profiles=(
            _uphill(),
            _downhill(),
            _uphill(),
        ),
    )

    assert result.estimates == (None, None, None)


def test_missing_electric_price_is_not_zero_cost() -> None:
    result = evaluate_trip_electric_energy(
        _routes(),
        vehicle=_electric_vehicle(),
        electricity_price_quote=None,
        terrain_profiles=(
            _uphill(),
            _downhill(),
            _uphill(),
        ),
    )

    assert result.estimates == (None, None, None)


def test_missing_toll_remains_separate_from_terrain_policy() -> None:
    routes = (
        RouteCandidate(1000, 500, None),
        RouteCandidate(1000, 600, Decimal(0)),
    )

    evaluation = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(_uphill(), _downhill()),
    )

    assert evaluation.terrain_applied

    candidates = tuple(
        DecisionCandidate(
            route=route,
            energy_estimate=estimate,
        )
        for route, estimate in zip(
            routes,
            evaluation.estimates,
            strict=True,
        )
        if route.toll_cost is not None and estimate is not None
    )

    decision = decide_route(
        candidates,
        value_of_time_per_hour=Decimal(0),
        candidate_count=len(routes),
        missing_data_present=True,
    )

    assert decision.eligible_count == 1
    assert decision.missing_data_present
    assert decision.recommended_route == routes[1]


def test_candidate_order_and_result_are_deterministic() -> None:
    routes = _routes()
    profiles = (
        _uphill(),
        _low_coverage(),
        _downhill(),
    )

    first = evaluate_trip_electric_energy(
        routes,
        vehicle=_electric_vehicle(),
        electricity_price_quote=_electric_quote(),
        terrain_profiles=profiles,
    )

    second = evaluate_trip_electric_energy(
        routes,
        vehicle=_electric_vehicle(),
        electricity_price_quote=_electric_quote(),
        terrain_profiles=profiles,
    )

    assert first == second
    assert len(first.estimates) == len(routes)
    assert first.applicability.blocking_candidate_indices == (1,)
