"""M7-D4 regression and safety tests for terrain-aware gasoline."""

from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample, TerrainProfile
from routevalue.application.terrain_energy import (
    TerrainEnergyResult,
    TerrainSegmentEnergy,
)
from routevalue.application.terrain_gasoline_consumption import (
    estimate_terrain_gasoline_consumption,
)
from routevalue.application.terrain_gasoline_evaluation import (
    estimate_terrain_gasoline_energy_if_available,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    normalize_terrain_profile,
)
from routevalue.domain.energy_consumption import (
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.models import (
    EnergyEstimate,
    GasolineConsumption,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


def _route(
    *,
    distance: int = 1000,
    toll: str = "0",
) -> RouteCandidate:
    return RouteCandidate(
        distance_meters=distance,
        duration_seconds=600,
        toll_cost=Decimal(toll),
    )


def _vehicle(
    *,
    mass: str | None = "1500",
) -> GasolineVehicleSpecification:
    vehicle_mass = (
        VehicleMass(
            kilograms=Decimal(mass),
            source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        )
        if mass is not None
        else None
    )

    return GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=vehicle_mass,
    )


def _quote(price: str = "4.50") -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal(price),
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )


def _terrain(
    elevations: tuple[str | None, ...],
) -> NormalizedTerrainProfile:
    assert len(elevations) >= 2

    distance = 1000

    samples = tuple(
        ElevationSample(
            point=RoutePoint(latitude=32.0, longitude=-117.0),
            distance_meters=distance * index // (len(elevations) - 1),
            elevation_meters=(Decimal(value) if value is not None else None),
        )
        for index, value in enumerate(elevations)
    )

    return normalize_terrain_profile(
        TerrainProfile(
            route_distance_meters=distance,
            samples=samples,
        )
    )


def _evaluate(
    *,
    terrain: NormalizedTerrainProfile | None = None,
    vehicle: GasolineVehicleSpecification | None = None,
    price: str = "4.50",
    route: RouteCandidate | None = None,
) -> EnergyEstimate:
    result = estimate_terrain_gasoline_energy_if_available(
        route if route is not None else _route(),
        vehicle=vehicle if vehicle is not None else _vehicle(),
        fuel_price_quote=_quote(price),
        terrain=terrain,
    )

    assert result is not None
    return result


def _gallons(result: EnergyEstimate) -> Decimal:
    assert isinstance(result.consumption, GasolineConsumption)
    return result.consumption.gallons


def test_no_terrain_matches_exact_m5_consumption() -> None:
    route = _route()
    vehicle = _vehicle()

    expected = estimate_baseline_gasoline_consumption(route, vehicle=vehicle)

    actual = _evaluate(route=route, vehicle=vehicle)

    assert actual.consumption == expected
    assert actual.cost == expected.gallons * _quote().price_per_gallon


def test_flat_terrain_matches_exact_baseline() -> None:
    baseline = _evaluate()
    flat = _evaluate(terrain=_terrain(("100", "100", "100")))

    assert flat == baseline


def test_missing_mass_matches_exact_baseline() -> None:
    vehicle = _vehicle(mass=None)

    baseline = _evaluate(vehicle=vehicle)
    with_terrain = _evaluate(
        vehicle=vehicle,
        terrain=_terrain(("100", "140")),
    )

    assert with_terrain == baseline


def test_unknown_elevations_do_not_create_energy() -> None:
    baseline = _evaluate()
    unavailable = _evaluate(terrain=_terrain(("100", None, None, "140")))

    assert unavailable == baseline


def test_uphill_consumption_increases_with_mass() -> None:
    climb = _terrain(("100", "140"))

    baseline = _evaluate()
    lighter = _evaluate(terrain=climb, vehicle=_vehicle(mass="1000"))
    heavier = _evaluate(terrain=climb, vehicle=_vehicle(mass="2000"))

    assert _gallons(heavier) > _gallons(lighter) > _gallons(baseline)


def test_downhill_consumption_is_nonnegative() -> None:
    descent = _terrain(("140", "100"))

    baseline = _evaluate()
    downhill = _evaluate(terrain=descent)

    assert Decimal(0) <= _gallons(downhill) < _gallons(baseline)


def test_price_does_not_change_physical_consumption() -> None:
    climb = _terrain(("100", "140"))

    cheap = _evaluate(terrain=climb, price="3")
    expensive = _evaluate(terrain=climb, price="6")

    assert cheap.consumption == expensive.consumption
    assert expensive.cost == cheap.cost * 2


def test_zero_fuel_price_is_not_missing() -> None:
    result = _evaluate(
        terrain=_terrain(("100", "140")),
        price="0",
    )

    assert result.cost == 0
    assert _gallons(result) > 0


def test_tolls_do_not_change_gasoline_consumption_or_cost() -> None:
    climb = _terrain(("100", "140"))

    no_toll = _evaluate(terrain=climb, route=_route(toll="0"))
    high_toll = _evaluate(terrain=climb, route=_route(toll="100"))

    assert no_toll == high_toll


def test_partial_terrain_keeps_unknown_intervals() -> None:
    profile = _terrain(("100", "120", None, "140", "160"))

    assert profile.coverage == Decimal("0.5")
    assert profile.unknown_distance_meters == 500

    adjusted = _evaluate(terrain=profile)
    baseline = _evaluate()

    assert _gallons(adjusted) > _gallons(baseline)


def test_large_descent_cannot_offset_other_segments() -> None:
    route = _route()
    vehicle = _vehicle()

    baseline = estimate_baseline_gasoline_consumption(route, vehicle=vehicle)

    terrain = TerrainEnergyResult(
        route_distance_meters=1000,
        segments=(
            TerrainSegmentEnergy(0, 500, Decimal(1)),
            TerrainSegmentEnergy(500, 1000, Decimal(-100)),
        ),
        usable_distance_meters=1000,
        unknown_distance_meters=0,
        coverage=Decimal(1),
        uphill_gravitational_kwh=Decimal(1),
        downhill_gravitational_kwh=Decimal(100),
    )

    result = estimate_terrain_gasoline_consumption(
        route,
        vehicle=vehicle,
        terrain=terrain,
    )

    # A downhill segment cannot generate a negative fuel credit.
    assert result.gallons > baseline.gallons / 2
    assert result.gallons >= 0


def test_malformed_terrain_distance_is_rejected() -> None:
    route = _route(distance=2000)

    with pytest.raises(ValueError, match="terrain distance"):
        _evaluate(
            route=route,
            terrain=_terrain(("100", "140")),
        )


def test_inconsistent_terrain_coverage_is_rejected() -> None:
    terrain = TerrainEnergyResult(
        route_distance_meters=1000,
        segments=(TerrainSegmentEnergy(0, 1000, Decimal(1)),),
        usable_distance_meters=1000,
        unknown_distance_meters=0,
        coverage=Decimal("0.5"),
        uphill_gravitational_kwh=Decimal(1),
        downhill_gravitational_kwh=Decimal(0),
    )

    with pytest.raises(ValueError, match="coverage"):
        estimate_terrain_gasoline_consumption(
            _route(),
            vehicle=_vehicle(),
            terrain=terrain,
        )


def test_zero_distance_preserves_zero_consumption() -> None:
    result = _evaluate(route=_route(distance=0))

    assert _gallons(result) == 0
    assert result.cost == 0


def test_repeated_evaluation_is_deterministic() -> None:
    climb = _terrain(("100", "140"))

    first = _evaluate(terrain=climb)
    second = _evaluate(terrain=climb)

    assert first == second


def test_existing_baseline_estimator_is_not_mutated() -> None:
    route = _route()
    vehicle = _vehicle()
    original = estimate_baseline_gasoline_consumption(route, vehicle=vehicle)

    _evaluate(terrain=_terrain(("100", "140")))

    after = estimate_baseline_gasoline_consumption(route, vehicle=vehicle)

    assert after == original
