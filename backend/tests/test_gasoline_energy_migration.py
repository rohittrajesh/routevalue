from decimal import Decimal

from routevalue.domain.energy_consumption import (
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.gasoline_energy import estimate_gasoline_energy
from routevalue.domain.models import (
    GasolineConsumption,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleProfile,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.infrastructure.energy.gasoline import (
    GasolineEnergyCostEstimator,
)


def test_migrated_gasoline_energy_preserves_exact_v1_cost() -> None:
    route = RouteCandidate(
        distance_meters=201_168,
        duration_seconds=7_200,
        toll_cost=Decimal("5.00"),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = GasolinePriceQuote(
        price_per_gallon=Decimal("4.00"),
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    estimate = estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price,
    )

    assert estimate.cost == Decimal("20.00")
    assert estimate.consumption == GasolineConsumption(
        gallons=Decimal(5),
    )


def test_migrated_gasoline_energy_uses_baseline_consumption_model() -> None:
    route = RouteCandidate(
        distance_meters=12_345,
        duration_seconds=1_200,
        toll_cost=Decimal(0),
    )
    legacy_vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal("31.7"),
        fuel_grade=GasolineGrade.PREMIUM,
    )
    specification = GasolineVehicleSpecification(
        combined_mpg=legacy_vehicle.fuel_efficiency_mpg,
        fuel_grade=legacy_vehicle.fuel_grade,
    )
    fuel_price = GasolinePriceQuote(
        price_per_gallon=Decimal("4.679"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    expected_consumption = estimate_baseline_gasoline_consumption(
        route,
        vehicle=specification,
    )

    estimate = estimate_gasoline_energy(
        route,
        vehicle=legacy_vehicle,
        fuel_price_quote=fuel_price,
    )

    assert estimate.consumption == expected_consumption
    assert estimate.cost == (expected_consumption.gallons * fuel_price.price_per_gallon)


def test_application_gasoline_estimator_surfaces_typed_consumption() -> None:
    route = RouteCandidate(
        distance_meters=201_168,
        duration_seconds=3_600,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = GasolinePriceQuote(
        price_per_gallon=Decimal("4.00"),
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )
    estimator = GasolineEnergyCostEstimator(
        vehicle=vehicle,
        fuel_price_quote=fuel_price,
    )

    estimate = estimator.estimate_energy(route)

    assert estimate is not None
    assert estimate.cost == Decimal("20.00")
    assert estimate.consumption == GasolineConsumption(
        gallons=Decimal(5),
    )
