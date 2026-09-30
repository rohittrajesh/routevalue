from datetime import UTC, datetime
from decimal import Decimal

import pytest

from routevalue.domain.gasoline_energy import (
    estimate_gasoline_energy,
    estimate_gasoline_energy_if_available,
)
from routevalue.domain.models import (
    FuelPriceQuote,
    FuelPriceSource,
    GasolineGrade,
    GasolineVehicleProfile,
    RouteCandidate,
)


def test_estimate_gasoline_energy_calculates_expected_cost() -> None:
    route = RouteCandidate(
        distance_meters=1_609_344,
        duration_seconds=3_600,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
    )

    estimate = estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price,
    )

    assert estimate.cost == Decimal("180.00")


def test_estimate_gasoline_energy_zero_distance_costs_zero() -> None:
    route = RouteCandidate(
        distance_meters=0,
        duration_seconds=0,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    estimate = estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price,
    )

    assert estimate.cost == Decimal(0)


def test_estimate_gasoline_energy_zero_fuel_price_costs_zero() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal(0),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    estimate = estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price,
    )

    assert estimate.cost == Decimal(0)


def test_estimate_gasoline_energy_rejects_mismatched_fuel_grade() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.PREMIUM,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    with pytest.raises(
        ValueError,
        match="fuel price grade must match vehicle fuel grade",
    ):
        estimate_gasoline_energy(
            route,
            vehicle=vehicle,
            fuel_price_quote=fuel_price,
        )


def test_estimate_gasoline_energy_preserves_decimal_precision() -> None:
    route = RouteCandidate(
        distance_meters=12_345,
        duration_seconds=1_200,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal("31.7"),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal("4.679"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    estimate = estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price,
    )

    expected_cost = Decimal(12_345) / Decimal("1609.344") / Decimal("31.7") * Decimal("4.679")

    assert estimate.cost == expected_cost


def test_estimate_gasoline_energy_does_not_round_to_currency_precision() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    estimate = estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price,
    )

    assert estimate.cost != estimate.cost.quantize(Decimal("0.01"))


def test_estimate_gasoline_energy_is_independent_of_price_source() -> None:
    route = RouteCandidate(
        distance_meters=20_000,
        duration_seconds=1_800,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(28),
        fuel_grade=GasolineGrade.REGULAR,
    )

    override_quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.40"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )
    local_quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.40"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
    )

    override_estimate = estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=override_quote,
    )
    local_estimate = estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=local_quote,
    )

    assert override_estimate == local_estimate


def test_estimate_gasoline_energy_if_available_returns_none_without_price() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )

    estimate = estimate_gasoline_energy_if_available(
        route,
        vehicle=vehicle,
        fuel_price_quote=None,
    )

    assert estimate is None


def test_estimate_gasoline_energy_if_available_returns_estimate_with_price() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    estimate = estimate_gasoline_energy_if_available(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price,
    )

    assert estimate == estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price,
    )


def test_estimate_gasoline_energy_if_available_does_not_hide_invalid_price() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.PREMIUM,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    with pytest.raises(
        ValueError,
        match="fuel price grade must match vehicle fuel grade",
    ):
        estimate_gasoline_energy_if_available(
            route,
            vehicle=vehicle,
            fuel_price_quote=fuel_price,
        )
