"""M7-E3 tests for terrain-aware BEV electricity-price integration."""

from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample, TerrainProfile
from routevalue.application.terrain_electric_evaluation import (
    estimate_terrain_electric_energy_if_available,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    normalize_terrain_profile,
)
from routevalue.domain.electric_energy import estimate_electric_energy
from routevalue.domain.models import (
    ElectricConsumption,
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    EnergyEstimate,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


def _route(
    *,
    distance: int = 1000,
    toll: str = "12.50",
) -> RouteCandidate:
    return RouteCandidate(
        distance_meters=distance,
        duration_seconds=600,
        toll_cost=Decimal(toll),
    )


def _vehicle(
    *,
    mass_kg: str | None = "2000",
) -> ElectricVehicleSpecification:
    mass = (
        VehicleMass(
            kilograms=Decimal(mass_kg),
            source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        )
        if mass_kg is not None
        else None
    )

    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=mass,
    )


def _quote(price: str = "0.30") -> ElectricityPriceQuote:
    return ElectricityPriceQuote(
        price_per_kilowatt_hour=Decimal(price),
    )


def _terrain(
    elevations: tuple[str | None, ...],
) -> NormalizedTerrainProfile:
    if len(elevations) < 2:
        raise ValueError("test terrain requires at least two samples")

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


def _estimate(
    *,
    vehicle: ElectricVehicleSpecification | None = None,
    quote: ElectricityPriceQuote | None = None,
    terrain: NormalizedTerrainProfile | None = None,
    route: RouteCandidate | None = None,
) -> EnergyEstimate:
    result = estimate_terrain_electric_energy_if_available(
        route if route is not None else _route(),
        vehicle=vehicle if vehicle is not None else _vehicle(),
        electricity_price_quote=quote if quote is not None else _quote(),
        terrain=terrain,
    )

    assert result is not None
    return result


def _kwh(estimate: EnergyEstimate) -> Decimal:
    assert isinstance(estimate.consumption, ElectricConsumption)
    return estimate.consumption.kilowatt_hours


def test_missing_terrain_matches_exact_m5_estimate() -> None:
    route = _route()
    vehicle = _vehicle()
    quote = _quote()

    expected = estimate_electric_energy(
        route,
        vehicle=vehicle,
        electricity_price_quote=quote,
    )

    actual = estimate_terrain_electric_energy_if_available(
        route,
        vehicle=vehicle,
        electricity_price_quote=quote,
        terrain=None,
    )

    assert actual == expected


def test_flat_terrain_matches_exact_baseline() -> None:
    baseline = _estimate()
    flat = _estimate(
        terrain=_terrain(("100", "100", "100")),
    )

    assert flat == baseline


def test_missing_mass_preserves_exact_baseline() -> None:
    vehicle = _vehicle(mass_kg=None)

    baseline = _estimate(vehicle=vehicle)
    result = _estimate(
        vehicle=vehicle,
        terrain=_terrain(("100", "120", "140")),
    )

    assert result == baseline


def test_uphill_increases_consumption_and_cost() -> None:
    baseline = _estimate()
    uphill = _estimate(
        terrain=_terrain(("100", "120", "140")),
    )

    assert _kwh(uphill) > _kwh(baseline)
    assert uphill.cost > baseline.cost


def test_downhill_reduces_consumption_and_cost() -> None:
    baseline = _estimate()
    downhill = _estimate(
        terrain=_terrain(("140", "120", "100")),
    )

    assert Decimal(0) <= _kwh(downhill) < _kwh(baseline)
    assert Decimal(0) <= downhill.cost < baseline.cost


def test_heavier_vehicle_requires_more_uphill_energy() -> None:
    terrain = _terrain(("100", "120", "140"))

    lighter = _estimate(
        vehicle=_vehicle(mass_kg="1000"),
        terrain=terrain,
    )
    heavier = _estimate(
        vehicle=_vehicle(mass_kg="2000"),
        terrain=terrain,
    )

    assert _kwh(heavier) > _kwh(lighter)
    assert heavier.cost > lighter.cost


def test_same_terrain_uses_selected_vehicle_mass() -> None:
    terrain = _terrain(("100", "120", "140"))

    first = _estimate(
        vehicle=_vehicle(mass_kg="1200"),
        terrain=terrain,
    )
    second = _estimate(
        vehicle=_vehicle(mass_kg="2400"),
        terrain=terrain,
    )

    assert first != second


def test_electricity_price_changes_cost_not_consumption() -> None:
    terrain = _terrain(("100", "120", "140"))

    cheap = _estimate(
        quote=_quote("0.20"),
        terrain=terrain,
    )
    expensive = _estimate(
        quote=_quote("0.40"),
        terrain=terrain,
    )

    assert cheap.consumption == expensive.consumption
    assert abs(expensive.cost - cheap.cost * 2) < Decimal("1e-24")


def test_known_zero_price_is_valid() -> None:
    result = _estimate(
        quote=_quote("0"),
        terrain=_terrain(("100", "120", "140")),
    )

    assert result.cost == 0
    assert _kwh(result) > 0


def test_missing_price_returns_none() -> None:
    result = estimate_terrain_electric_energy_if_available(
        _route(),
        vehicle=_vehicle(),
        electricity_price_quote=None,
        terrain=_terrain(("100", "120", "140")),
    )

    assert result is None


def test_missing_elevations_preserve_baseline() -> None:
    baseline = _estimate()
    result = _estimate(
        terrain=_terrain(("100", None, "140")),
    )

    assert result == baseline


def test_tolls_are_separate_from_electricity_cost() -> None:
    terrain = _terrain(("100", "120", "140"))

    no_toll = _estimate(
        route=_route(toll="0"),
        terrain=terrain,
    )
    high_toll = _estimate(
        route=_route(toll="100"),
        terrain=terrain,
    )

    assert no_toll == high_toll


def test_mismatched_route_distance_is_rejected() -> None:
    with pytest.raises(ValueError, match="terrain distance"):
        _estimate(
            route=_route(distance=2000),
            terrain=_terrain(("100", "120", "140")),
        )


def test_zero_distance_without_terrain_returns_zero() -> None:
    result = _estimate(route=_route(distance=0))

    assert _kwh(result) == 0
    assert result.cost == 0


def test_evaluation_is_deterministic() -> None:
    terrain = _terrain(("100", "120", "140"))

    first = _estimate(terrain=terrain)
    second = _estimate(terrain=terrain)

    assert first == second
