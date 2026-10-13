"""Tests for pure electric estimation and the EV estimator adapter."""

from decimal import Decimal

from routevalue.application.ports import EnergyCostEstimator
from routevalue.domain.electric_energy import (
    estimate_electric_energy,
    estimate_electric_energy_if_available,
)
from routevalue.domain.models import (
    ElectricConsumption,
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    RouteCandidate,
)
from routevalue.infrastructure.energy.electric import (
    ElectricEnergyCostEstimator,
)


def _vehicle() -> ElectricVehicleSpecification:
    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
    )


def _quote(
    price: str = "0.31",
) -> ElectricityPriceQuote:
    return ElectricityPriceQuote(
        price_per_kilowatt_hour=Decimal(price),
    )


def _route(
    distance_meters: int = 201_168,
) -> RouteCandidate:
    return RouteCandidate(
        distance_meters=distance_meters,
        duration_seconds=3600,
        toll_cost=Decimal("4.00"),
    )


def test_electric_energy_calculates_consumption_and_cost() -> None:
    """125 miles at 0.30 kWh/mile consumes 37.5 kWh."""

    estimate = estimate_electric_energy(
        _route(),
        vehicle=_vehicle(),
        electricity_price_quote=_quote(),
    )

    assert estimate.consumption == ElectricConsumption(
        kilowatt_hours=Decimal("37.5"),
    )
    assert estimate.cost == Decimal("11.625")


def test_electric_energy_preserves_decimal_precision() -> None:
    """Energy and money calculations must not round prematurely."""

    route = _route(distance_meters=12_345)
    vehicle = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.287"),
    )
    quote = _quote("0.3157")

    estimate = estimate_electric_energy(
        route,
        vehicle=vehicle,
        electricity_price_quote=quote,
    )

    expected_kwh = Decimal(12_345) / Decimal("1609.344") * Decimal("0.287")
    expected_cost = expected_kwh * Decimal("0.3157")

    assert isinstance(estimate.consumption, ElectricConsumption)
    assert estimate.consumption.kilowatt_hours == expected_kwh
    assert estimate.cost == expected_cost
    assert estimate.cost != estimate.cost.quantize(Decimal("0.01"))


def test_zero_distance_produces_zero_consumption_and_cost() -> None:
    estimate = estimate_electric_energy(
        _route(distance_meters=0),
        vehicle=_vehicle(),
        electricity_price_quote=_quote(),
    )

    assert estimate.consumption == ElectricConsumption(
        kilowatt_hours=Decimal(0),
    )
    assert estimate.cost == Decimal(0)


def test_zero_electricity_price_is_known_not_missing() -> None:
    estimate = estimate_electric_energy(
        _route(),
        vehicle=_vehicle(),
        electricity_price_quote=_quote("0"),
    )

    assert estimate.cost == Decimal(0)
    assert isinstance(estimate.consumption, ElectricConsumption)
    assert estimate.consumption.kilowatt_hours == Decimal("37.5")


def test_energy_cost_does_not_include_tolls() -> None:
    """The authoritative decision engine adds tolls separately."""

    route = RouteCandidate(
        distance_meters=201_168,
        duration_seconds=3600,
        toll_cost=Decimal("100.00"),
    )

    estimate = estimate_electric_energy(
        route,
        vehicle=_vehicle(),
        electricity_price_quote=_quote(),
    )

    assert estimate.cost == Decimal("11.625")


def test_missing_electricity_quote_produces_no_estimate() -> None:
    estimate = estimate_electric_energy_if_available(
        _route(),
        vehicle=_vehicle(),
        electricity_price_quote=None,
    )

    assert estimate is None


def test_available_electricity_quote_produces_estimate() -> None:
    route = _route()
    vehicle = _vehicle()
    quote = _quote()

    estimate = estimate_electric_energy_if_available(
        route,
        vehicle=vehicle,
        electricity_price_quote=quote,
    )

    assert estimate == estimate_electric_energy(
        route,
        vehicle=vehicle,
        electricity_price_quote=quote,
    )


def test_electric_adapter_implements_existing_energy_port() -> None:
    estimator: EnergyCostEstimator = ElectricEnergyCostEstimator(
        vehicle=_vehicle(),
        electricity_price_quote=_quote(),
    )

    estimate = estimator.estimate_energy(_route())

    assert estimate is not None
    assert estimate.cost == Decimal("11.625")
    assert isinstance(estimate.consumption, ElectricConsumption)
    assert estimate.consumption.kilowatt_hours == Decimal("37.5")


def test_electric_adapter_preserves_missing_price_semantics() -> None:
    estimator: EnergyCostEstimator = ElectricEnergyCostEstimator(
        vehicle=_vehicle(),
        electricity_price_quote=None,
    )

    assert estimator.estimate_energy(_route()) is None
