"""M7-D3 tests for terrain-aware gasoline energy and price integration."""

from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample, TerrainProfile
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


def _route() -> RouteCandidate:
    return RouteCandidate(
        distance_meters=1000,
        duration_seconds=600,
        toll_cost=Decimal("12.50"),
    )


def _vehicle(
    *,
    mass_kg: str | None = "1500",
    grade: GasolineGrade = GasolineGrade.REGULAR,
) -> GasolineVehicleSpecification:
    mass = (
        VehicleMass(
            kilograms=Decimal(mass_kg),
            source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        )
        if mass_kg is not None
        else None
    )

    return GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=grade,
        vehicle_mass=mass,
    )


def _quote(
    price: str = "4.50",
    *,
    grade: GasolineGrade = GasolineGrade.REGULAR,
) -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal(price),
        fuel_grade=grade,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )


def _terrain(
    elevations: tuple[str | None, ...],
) -> NormalizedTerrainProfile:
    if len(elevations) < 2:
        raise ValueError("test profile requires two observations")

    route_distance = _route().distance_meters
    sample_count = len(elevations)

    profile = TerrainProfile(
        route_distance_meters=route_distance,
        samples=tuple(
            ElevationSample(
                point=RoutePoint(latitude=32.0, longitude=-117.0),
                distance_meters=route_distance * index // (sample_count - 1),
                elevation_meters=Decimal(elevation) if elevation is not None else None,
            )
            for index, elevation in enumerate(elevations)
        ),
    )

    return normalize_terrain_profile(profile)


def _estimate(
    *,
    vehicle: GasolineVehicleSpecification | None = None,
    quote: GasolinePriceQuote | None = None,
    terrain: NormalizedTerrainProfile | None = None,
) -> EnergyEstimate | None:
    selected_vehicle = vehicle if vehicle is not None else _vehicle()
    selected_quote = quote if quote is not None else _quote()

    return estimate_terrain_gasoline_energy_if_available(
        _route(),
        vehicle=selected_vehicle,
        fuel_price_quote=selected_quote,
        terrain=terrain,
    )


def test_missing_terrain_preserves_exact_m5_baseline() -> None:
    vehicle = _vehicle()
    result = _estimate(vehicle=vehicle)

    assert result is not None
    expected = estimate_baseline_gasoline_consumption(_route(), vehicle=vehicle)

    assert result.consumption == expected
    assert result.cost == expected.gallons * _quote().price_per_gallon


def test_flat_terrain_preserves_exact_m5_baseline() -> None:
    vehicle = _vehicle()

    baseline = _estimate(vehicle=vehicle)
    flat = _estimate(
        vehicle=vehicle,
        terrain=_terrain(("100", "100", "100")),
    )

    assert flat == baseline


def test_missing_mass_preserves_baseline_with_available_terrain() -> None:
    vehicle = _vehicle(mass_kg=None)

    baseline = _estimate(vehicle=vehicle)
    adjusted = _estimate(
        vehicle=vehicle,
        terrain=_terrain(("100", "120", "140")),
    )

    assert adjusted == baseline


def test_uphill_increases_gallons_and_cost() -> None:
    baseline = _estimate()
    uphill = _estimate(terrain=_terrain(("100", "120", "140")))

    assert baseline is not None
    assert uphill is not None
    assert isinstance(baseline.consumption, GasolineConsumption)
    assert isinstance(uphill.consumption, GasolineConsumption)

    assert uphill.consumption.gallons > baseline.consumption.gallons
    assert uphill.cost > baseline.cost


def test_downhill_decreases_gallons_and_cost() -> None:
    baseline = _estimate()
    downhill = _estimate(terrain=_terrain(("140", "120", "100")))

    assert baseline is not None
    assert downhill is not None
    assert isinstance(baseline.consumption, GasolineConsumption)
    assert isinstance(downhill.consumption, GasolineConsumption)

    assert downhill.consumption.gallons < baseline.consumption.gallons
    assert Decimal(0) <= downhill.cost < baseline.cost


def test_higher_vehicle_mass_increases_uphill_correction() -> None:
    terrain = _terrain(("100", "120", "140"))

    lighter = _estimate(
        vehicle=_vehicle(mass_kg="1000"),
        terrain=terrain,
    )
    heavier = _estimate(
        vehicle=_vehicle(mass_kg="2000"),
        terrain=terrain,
    )

    assert lighter is not None
    assert heavier is not None
    assert heavier.cost > lighter.cost


def test_mass_is_recomputed_for_each_selected_vehicle() -> None:
    terrain = _terrain(("100", "120", "140"))

    first = _estimate(
        vehicle=_vehicle(mass_kg="1000"),
        terrain=terrain,
    )
    second = _estimate(
        vehicle=_vehicle(mass_kg="2000"),
        terrain=terrain,
    )

    assert first is not None
    assert second is not None
    assert first != second


def test_price_changes_cost_not_consumption() -> None:
    terrain = _terrain(("100", "120", "140"))

    cheap = _estimate(
        quote=_quote("3.50"),
        terrain=terrain,
    )
    expensive = _estimate(
        quote=_quote("5.50"),
        terrain=terrain,
    )

    assert cheap is not None
    assert expensive is not None
    assert cheap.consumption == expensive.consumption
    assert expensive.cost > cheap.cost


def test_zero_price_remains_known_and_valid() -> None:
    result = _estimate(
        quote=_quote("0"),
        terrain=_terrain(("100", "120", "140")),
    )

    assert result is not None
    assert result.cost == 0
    assert isinstance(result.consumption, GasolineConsumption)
    assert result.consumption.gallons > 0


def test_missing_price_returns_no_estimate() -> None:
    result = estimate_terrain_gasoline_energy_if_available(
        _route(),
        vehicle=_vehicle(),
        fuel_price_quote=None,
        terrain=_terrain(("100", "120", "140")),
    )

    assert result is None


def test_mismatched_gasoline_grade_is_rejected() -> None:
    with pytest.raises(ValueError, match="fuel price grade"):
        _estimate(
            vehicle=_vehicle(grade=GasolineGrade.PREMIUM),
            quote=_quote(grade=GasolineGrade.REGULAR),
        )


def test_mismatched_route_distance_is_rejected() -> None:
    wrong_route = RouteCandidate(
        distance_meters=2000,
        duration_seconds=600,
        toll_cost=Decimal(0),
    )

    with pytest.raises(ValueError, match="terrain distance"):
        estimate_terrain_gasoline_energy_if_available(
            wrong_route,
            vehicle=_vehicle(),
            fuel_price_quote=_quote(),
            terrain=_terrain(("100", "120", "140")),
        )


def test_missing_elevation_preserves_baseline() -> None:
    baseline = _estimate()
    missing = _estimate(terrain=_terrain(("100", None, "140")))

    assert missing == baseline


def test_toll_does_not_enter_energy_cost() -> None:
    terrain = _terrain(("100", "120", "140"))
    first = _estimate(terrain=terrain)

    route_without_toll = RouteCandidate(
        distance_meters=1000,
        duration_seconds=600,
        toll_cost=Decimal(0),
    )

    second = estimate_terrain_gasoline_energy_if_available(
        route_without_toll,
        vehicle=_vehicle(),
        fuel_price_quote=_quote(),
        terrain=terrain,
    )

    assert first == second


def test_evaluation_is_deterministic() -> None:
    terrain = _terrain(("100", "120", "140"))

    assert _estimate(terrain=terrain) == _estimate(terrain=terrain)
