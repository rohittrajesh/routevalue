from decimal import Decimal

import pytest

from routevalue.application.ports import EnergyCostEstimator
from routevalue.domain.models import (
    FuelPriceQuote,
    FuelPriceSource,
    GasolineGrade,
    GasolineVehicleProfile,
    RouteCandidate,
)
from routevalue.infrastructure.energy.gasoline import (
    GasolineEnergyCostEstimator,
)


def test_gasoline_energy_estimator_calculates_route_cost() -> None:
    route = RouteCandidate(
        distance_meters=1_609_344,
        duration_seconds=3_600,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price_quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    estimator: EnergyCostEstimator = GasolineEnergyCostEstimator(
        vehicle=vehicle,
        fuel_price_quote=fuel_price_quote,
    )

    estimate = estimator.estimate_energy(route)

    assert estimate is not None
    assert estimate.cost == Decimal("180.00")


def test_gasoline_energy_estimator_returns_none_without_fuel_price() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )

    estimator: EnergyCostEstimator = GasolineEnergyCostEstimator(
        vehicle=vehicle,
        fuel_price_quote=None,
    )

    estimate = estimator.estimate_energy(route)

    assert estimate is None


def test_gasoline_energy_estimator_does_not_hide_invalid_domain_context() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.PREMIUM,
    )
    fuel_price_quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    estimator: EnergyCostEstimator = GasolineEnergyCostEstimator(
        vehicle=vehicle,
        fuel_price_quote=fuel_price_quote,
    )

    with pytest.raises(
        ValueError,
        match="fuel price grade must match vehicle fuel grade",
    ):
        estimator.estimate_energy(route)
