"""Network-free integration tests for V2 mass-aware terrain energy."""

from dataclasses import replace
from decimal import Decimal

from routevalue.application.terrain import GeometryFidelity
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    NormalizedTerrainSegment,
    TerrainSegmentStatus,
)
from routevalue.application.terrain_trip_energy import (
    TripTerrainEnergyResult,
    evaluate_trip_electric_energy,
    evaluate_trip_gasoline_energy,
)
from routevalue.domain.models import (
    ElectricConsumption,
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


def _route() -> RouteCandidate:
    return RouteCandidate(
        distance_meters=10000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )


def _uphill_profile() -> NormalizedTerrainProfile:
    return NormalizedTerrainProfile(
        route_distance_meters=10000,
        segments=(
            NormalizedTerrainSegment(
                start_distance_meters=0,
                end_distance_meters=5000,
                elevation_change_meters=Decimal(100),
                status=TerrainSegmentStatus.USABLE,
            ),
            NormalizedTerrainSegment(
                start_distance_meters=5000,
                end_distance_meters=10000,
                elevation_change_meters=Decimal(100),
                status=TerrainSegmentStatus.USABLE,
            ),
        ),
        geometry_fidelity=GeometryFidelity.DETAILED,
    )


def _mass(kilograms: int) -> VehicleMass:
    return VehicleMass(
        kilograms=Decimal(kilograms),
        source=VehicleMassSource.USER_PROVIDED,
        source_reference="Synthetic regression-test fixture",
    )


def _gasoline_price() -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )


def _gasoline_used(
    result: TripTerrainEnergyResult,
    index: int = 0,
) -> Decimal:
    estimate = result.estimates[index]
    assert estimate is not None

    consumption = estimate.consumption
    assert isinstance(consumption, GasolineConsumption)
    return consumption.gallons


def _electricity_used(
    result: TripTerrainEnergyResult,
    index: int = 0,
) -> Decimal:
    estimate = result.estimates[index]
    assert estimate is not None

    consumption = estimate.consumption
    assert isinstance(consumption, ElectricConsumption)
    return consumption.kilowatt_hours


def test_gasoline_mass_enables_terrain_and_changes_consumption() -> None:
    route = _route()
    terrain = _uphill_profile()

    vehicle = GasolineVehicleSpecification(
        combined_mpg=Decimal(26),
        fuel_grade=GasolineGrade.PREMIUM,
    )

    def evaluate(mass: VehicleMass | None) -> TripTerrainEnergyResult:
        return evaluate_trip_gasoline_energy(
            (route,),
            vehicle=replace(vehicle, vehicle_mass=mass),
            fuel_price_quote=_gasoline_price(),
            terrain_profiles=(terrain,),
        )

    missing_mass = evaluate(None)
    light_vehicle = evaluate(_mass(1500))
    heavy_vehicle = evaluate(_mass(2200))

    assert missing_mass.terrain_applied is False
    assert missing_mass.missing_vehicle_mass is True

    assert light_vehicle.terrain_applied is True
    assert heavy_vehicle.terrain_applied is True
    assert light_vehicle.missing_vehicle_mass is False
    assert light_vehicle.applicability.candidate_coverages == (Decimal(1),)

    assert (
        _gasoline_used(missing_mass) < _gasoline_used(light_vehicle) < _gasoline_used(heavy_vehicle)
    )


def test_electric_mass_enables_terrain_and_changes_consumption() -> None:
    route = _route()
    terrain = _uphill_profile()

    vehicle = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
    )

    def evaluate(mass: VehicleMass | None) -> TripTerrainEnergyResult:
        return evaluate_trip_electric_energy(
            (route,),
            vehicle=replace(vehicle, vehicle_mass=mass),
            electricity_price_quote=ElectricityPriceQuote(
                price_per_kilowatt_hour=Decimal("0.25"),
            ),
            terrain_profiles=(terrain,),
        )

    missing_mass = evaluate(None)
    light_vehicle = evaluate(_mass(1700))
    heavy_vehicle = evaluate(_mass(2400))

    assert missing_mass.terrain_applied is False
    assert missing_mass.missing_vehicle_mass is True

    assert light_vehicle.terrain_applied is True
    assert heavy_vehicle.terrain_applied is True
    assert heavy_vehicle.applicability.candidate_coverages == (Decimal(1),)

    assert (
        _electricity_used(missing_mass)
        < _electricity_used(light_vehicle)
        < _electricity_used(heavy_vehicle)
    )


def test_missing_route_terrain_forces_trip_wide_gasoline_baseline() -> None:
    route = _route()

    vehicle = GasolineVehicleSpecification(
        combined_mpg=Decimal(26),
        fuel_grade=GasolineGrade.PREMIUM,
        vehicle_mass=_mass(1900),
    )

    result = evaluate_trip_gasoline_energy(
        (route, route),
        vehicle=vehicle,
        fuel_price_quote=_gasoline_price(),
        terrain_profiles=(_uphill_profile(), None),
    )

    baseline = evaluate_trip_gasoline_energy(
        (route,),
        vehicle=vehicle,
        fuel_price_quote=_gasoline_price(),
        terrain_profiles=(None,),
    )

    assert result.terrain_applied is False
    assert result.missing_vehicle_mass is False
    assert result.applicability.use_terrain is False

    assert result.applicability.candidate_coverages == (
        Decimal(1),
        None,
    )

    assert _gasoline_used(result, 0) == _gasoline_used(baseline)
    assert _gasoline_used(result, 1) == _gasoline_used(baseline)


def test_missing_route_terrain_forces_trip_wide_electric_baseline() -> None:
    route = _route()

    vehicle = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=_mass(2100),
    )

    quote = ElectricityPriceQuote(
        price_per_kilowatt_hour=Decimal("0.25"),
    )

    result = evaluate_trip_electric_energy(
        (route, route),
        vehicle=vehicle,
        electricity_price_quote=quote,
        terrain_profiles=(_uphill_profile(), None),
    )

    baseline = evaluate_trip_electric_energy(
        (route,),
        vehicle=vehicle,
        electricity_price_quote=quote,
        terrain_profiles=(None,),
    )

    assert result.terrain_applied is False
    assert result.missing_vehicle_mass is False
    assert result.applicability.use_terrain is False

    assert _electricity_used(result, 0) == _electricity_used(baseline)
    assert _electricity_used(result, 1) == _electricity_used(baseline)
