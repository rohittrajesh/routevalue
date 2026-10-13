"""M7-E4 regression and safety tests for terrain-aware BEV energy."""

from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample, TerrainProfile
from routevalue.application.terrain_electric_consumption import (
    estimate_terrain_electric_consumption,
)
from routevalue.application.terrain_electric_evaluation import (
    estimate_terrain_electric_energy_if_available,
)
from routevalue.application.terrain_energy import (
    TerrainEnergyResult,
    TerrainSegmentEnergy,
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
    toll: str = "0",
) -> RouteCandidate:
    return RouteCandidate(
        distance_meters=distance,
        duration_seconds=600,
        toll_cost=Decimal(toll),
    )


def _vehicle(
    *,
    mass: str | None = "2000",
) -> ElectricVehicleSpecification:
    vehicle_mass = (
        VehicleMass(
            kilograms=Decimal(mass),
            source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        )
        if mass is not None
        else None
    )

    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=vehicle_mass,
    )


def _quote(price: str = "0.30") -> ElectricityPriceQuote:
    return ElectricityPriceQuote(price_per_kilowatt_hour=Decimal(price))


def _terrain(
    elevations: tuple[str | None, ...],
) -> NormalizedTerrainProfile:
    if len(elevations) < 2:
        raise ValueError("test terrain requires at least two elevations")

    distance = 1000

    samples = tuple(
        ElevationSample(
            point=RoutePoint(
                latitude=32.0,
                longitude=-117.0,
            ),
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
    vehicle: ElectricVehicleSpecification | None = None,
    price: str = "0.30",
    route: RouteCandidate | None = None,
) -> EnergyEstimate:
    result = estimate_terrain_electric_energy_if_available(
        route if route is not None else _route(),
        vehicle=vehicle if vehicle is not None else _vehicle(),
        electricity_price_quote=_quote(price),
        terrain=terrain,
    )

    assert result is not None
    return result


def _kwh(result: EnergyEstimate) -> Decimal:
    assert isinstance(result.consumption, ElectricConsumption)
    return result.consumption.kilowatt_hours


def test_no_terrain_matches_exact_m5_estimate() -> None:
    route = _route()
    vehicle = _vehicle()
    price = _quote()

    baseline = estimate_electric_energy(
        route,
        vehicle=vehicle,
        electricity_price_quote=price,
    )

    actual = _evaluate(
        route=route,
        vehicle=vehicle,
    )

    assert actual == baseline


def test_flat_terrain_matches_exact_m5_estimate() -> None:
    baseline = _evaluate()

    flat = _evaluate(terrain=_terrain(("100", "100", "100")))

    assert flat == baseline


def test_missing_vehicle_mass_preserves_baseline() -> None:
    vehicle = _vehicle(mass=None)
    baseline = _evaluate(vehicle=vehicle)

    adjusted = _evaluate(
        vehicle=vehicle,
        terrain=_terrain(("100", "120", "140")),
    )

    assert adjusted == baseline


def test_unknown_elevations_do_not_create_energy() -> None:
    baseline = _evaluate()

    unavailable = _evaluate(terrain=_terrain(("100", None, None, "140")))

    assert unavailable == baseline


def test_uphill_consumption_increases_with_mass() -> None:
    climb = _terrain(("100", "140"))

    baseline = _evaluate()

    lighter = _evaluate(
        terrain=climb,
        vehicle=_vehicle(mass="1000"),
    )

    heavier = _evaluate(
        terrain=climb,
        vehicle=_vehicle(mass="2000"),
    )

    assert _kwh(heavier) > _kwh(lighter) > _kwh(baseline)


def test_downhill_consumption_is_nonnegative() -> None:
    descent = _terrain(("140", "100"))

    baseline = _evaluate()
    downhill = _evaluate(terrain=descent)

    assert Decimal(0) <= _kwh(downhill) < _kwh(baseline)
    assert downhill.cost >= 0


def test_equal_ascent_and_descent_do_not_cancel_losses() -> None:
    # The normalization median filter may smooth the hilltop,
    # but still preserves some climb and descent.
    hill = _terrain(("100", "110", "120", "110", "100"))

    baseline = _evaluate()
    adjusted = _evaluate(terrain=hill)

    # Drive and regenerative efficiencies are intentionally asymmetric.
    assert _kwh(adjusted) > _kwh(baseline)


def test_partial_terrain_preserves_unknown_intervals() -> None:
    partial = _terrain(("100", "120", None, "140", "160"))

    assert partial.coverage == Decimal("0.5")
    assert partial.unknown_distance_meters == 500

    baseline = _evaluate()
    adjusted = _evaluate(terrain=partial)

    # Known uphill intervals increase kWh, while unknown ones are
    # retained at their original baseline allocations.
    assert _kwh(adjusted) > _kwh(baseline)


def test_price_changes_cost_not_kwh() -> None:
    hill = _terrain(("100", "140"))

    cheap = _evaluate(
        terrain=hill,
        price="0.20",
    )

    expensive = _evaluate(
        terrain=hill,
        price="0.40",
    )

    assert cheap.consumption == expensive.consumption
    assert abs(expensive.cost - cheap.cost * 2) < Decimal("1e-24")


def test_zero_price_is_valid_and_known() -> None:
    result = _evaluate(
        terrain=_terrain(("100", "140")),
        price="0",
    )

    assert _kwh(result) > 0
    assert result.cost == 0


def test_tolls_are_excluded_from_electricity_cost() -> None:
    hill = _terrain(("100", "140"))

    no_toll = _evaluate(
        terrain=hill,
        route=_route(toll="0"),
    )

    high_toll = _evaluate(
        terrain=hill,
        route=_route(toll="100"),
    )

    assert no_toll == high_toll


def test_excessive_regeneration_never_produces_negative_kwh() -> None:
    route = _route()
    vehicle = _vehicle()

    terrain = TerrainEnergyResult(
        route_distance_meters=1000,
        segments=(
            TerrainSegmentEnergy(
                start_distance_meters=0,
                end_distance_meters=500,
                gravitational_kwh=Decimal(-100),
            ),
            TerrainSegmentEnergy(
                start_distance_meters=500,
                end_distance_meters=1000,
                gravitational_kwh=Decimal(-100),
            ),
        ),
        usable_distance_meters=1000,
        unknown_distance_meters=0,
        coverage=Decimal(1),
        uphill_gravitational_kwh=Decimal(0),
        downhill_gravitational_kwh=Decimal(200),
    )

    result = estimate_terrain_electric_consumption(
        route,
        vehicle=vehicle,
        terrain=terrain,
    )

    # The current sum-of-corrections implementation can leave a tiny
    # positive Decimal residual after all segments clamp to zero.
    assert Decimal(0) <= result.kilowatt_hours < Decimal("1e-24")


def test_descent_cannot_create_credit_against_uphill_segments() -> None:
    route = _route()
    vehicle = _vehicle()

    baseline = estimate_electric_energy(
        route,
        vehicle=vehicle,
        electricity_price_quote=_quote(),
    )

    terrain = TerrainEnergyResult(
        route_distance_meters=1000,
        segments=(
            TerrainSegmentEnergy(
                start_distance_meters=0,
                end_distance_meters=500,
                gravitational_kwh=Decimal(1),
            ),
            TerrainSegmentEnergy(
                start_distance_meters=500,
                end_distance_meters=1000,
                gravitational_kwh=Decimal(-100),
            ),
        ),
        usable_distance_meters=1000,
        unknown_distance_meters=0,
        coverage=Decimal(1),
        uphill_gravitational_kwh=Decimal(1),
        downhill_gravitational_kwh=Decimal(100),
    )

    adjusted = estimate_terrain_electric_consumption(
        route,
        vehicle=vehicle,
        terrain=terrain,
    )

    assert isinstance(baseline.consumption, ElectricConsumption)

    # The uphill segment still consumes its baseline share plus
    # gravitational energy even when the descent is extreme.
    assert adjusted.kilowatt_hours > baseline.consumption.kilowatt_hours / 2


def test_inconsistent_terrain_coverage_is_rejected() -> None:
    terrain = TerrainEnergyResult(
        route_distance_meters=1000,
        segments=(
            TerrainSegmentEnergy(
                start_distance_meters=0,
                end_distance_meters=1000,
                gravitational_kwh=Decimal(1),
            ),
        ),
        usable_distance_meters=1000,
        unknown_distance_meters=0,
        coverage=Decimal("0.5"),
        uphill_gravitational_kwh=Decimal(1),
        downhill_gravitational_kwh=Decimal(0),
    )

    with pytest.raises(ValueError, match="coverage"):
        estimate_terrain_electric_consumption(
            _route(),
            vehicle=_vehicle(),
            terrain=terrain,
        )


def test_inconsistent_gravitational_energy_is_rejected() -> None:
    terrain = TerrainEnergyResult(
        route_distance_meters=1000,
        segments=(
            TerrainSegmentEnergy(
                start_distance_meters=0,
                end_distance_meters=1000,
                gravitational_kwh=Decimal("0.5"),
            ),
        ),
        usable_distance_meters=1000,
        unknown_distance_meters=0,
        coverage=Decimal(1),
        uphill_gravitational_kwh=Decimal(999),
        downhill_gravitational_kwh=Decimal(0),
    )

    with pytest.raises(ValueError, match="uphill energy"):
        estimate_terrain_electric_consumption(
            _route(),
            vehicle=_vehicle(),
            terrain=terrain,
        )


def test_mismatched_route_distance_is_rejected() -> None:
    with pytest.raises(ValueError, match="terrain distance"):
        _evaluate(
            route=_route(distance=2000),
            terrain=_terrain(("100", "140")),
        )


def test_zero_distance_returns_zero_baseline() -> None:
    result = _evaluate(route=_route(distance=0))

    assert _kwh(result) == 0
    assert result.cost == 0


def test_repeated_evaluation_is_deterministic() -> None:
    hill = _terrain(("100", "140"))

    first = _evaluate(terrain=hill)
    second = _evaluate(terrain=hill)

    assert first == second


def test_original_m5_estimator_is_unchanged() -> None:
    route = _route()
    vehicle = _vehicle()
    price = _quote()

    before = estimate_electric_energy(
        route,
        vehicle=vehicle,
        electricity_price_quote=price,
    )

    _evaluate(
        route=route,
        vehicle=vehicle,
        terrain=_terrain(("100", "140")),
    )

    after = estimate_electric_energy(
        route,
        vehicle=vehicle,
        electricity_price_quote=price,
    )

    assert after == before
