from decimal import Decimal

from routevalue.domain.energy_consumption import (
    estimate_baseline_electric_consumption,
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.models import (
    ElectricConsumption,
    ElectricVehicleSpecification,
    GasolineConsumption,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
)


def test_baseline_gasoline_consumption_calculates_expected_gallons() -> None:
    route = RouteCandidate(
        distance_meters=201_168,
        duration_seconds=7_200,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleSpecification(
        combined_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )

    consumption = estimate_baseline_gasoline_consumption(
        route,
        vehicle=vehicle,
    )

    assert consumption == GasolineConsumption(
        gallons=Decimal(5),
    )


def test_baseline_gasoline_consumption_allows_zero_distance() -> None:
    route = RouteCandidate(
        distance_meters=0,
        duration_seconds=0,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )

    consumption = estimate_baseline_gasoline_consumption(
        route,
        vehicle=vehicle,
    )

    assert consumption.gallons == Decimal(0)


def test_baseline_gasoline_consumption_preserves_decimal_precision() -> None:
    route = RouteCandidate(
        distance_meters=12_345,
        duration_seconds=1_200,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleSpecification(
        combined_mpg=Decimal("31.7"),
        fuel_grade=GasolineGrade.PREMIUM,
    )

    consumption = estimate_baseline_gasoline_consumption(
        route,
        vehicle=vehicle,
    )

    expected = Decimal(12_345) / Decimal("1609.344") / Decimal("31.7")

    assert consumption.gallons == expected


def test_baseline_electric_consumption_calculates_expected_kilowatt_hours() -> None:
    route = RouteCandidate(
        distance_meters=201_168,
        duration_seconds=3_600,
        toll_cost=Decimal(0),
    )
    vehicle = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
    )

    consumption = estimate_baseline_electric_consumption(
        route,
        vehicle=vehicle,
    )

    assert consumption == ElectricConsumption(
        kilowatt_hours=Decimal("37.5"),
    )


def test_baseline_electric_consumption_allows_zero_distance() -> None:
    route = RouteCandidate(
        distance_meters=0,
        duration_seconds=0,
        toll_cost=Decimal(0),
    )
    vehicle = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.28"),
    )

    consumption = estimate_baseline_electric_consumption(
        route,
        vehicle=vehicle,
    )

    assert consumption.kilowatt_hours == Decimal(0)


def test_baseline_electric_consumption_preserves_decimal_precision() -> None:
    route = RouteCandidate(
        distance_meters=12_345,
        duration_seconds=1_200,
        toll_cost=Decimal(0),
    )
    vehicle = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.287"),
    )

    consumption = estimate_baseline_electric_consumption(
        route,
        vehicle=vehicle,
    )

    expected = Decimal(12_345) / Decimal("1609.344") * Decimal("0.287")

    assert consumption.kilowatt_hours == expected
