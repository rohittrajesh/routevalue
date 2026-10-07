from decimal import Decimal

import pytest

from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
)


def test_gasoline_vehicle_specification_accepts_combined_only_values() -> None:
    specification = GasolineVehicleSpecification(
        combined_mpg=Decimal("31.5"),
        fuel_grade=GasolineGrade.REGULAR,
    )

    assert specification.combined_mpg == Decimal("31.5")
    assert specification.fuel_grade is GasolineGrade.REGULAR
    assert specification.city_mpg is None
    assert specification.highway_mpg is None


def test_gasoline_vehicle_specification_accepts_city_highway_and_combined_values() -> None:
    specification = GasolineVehicleSpecification(
        city_mpg=Decimal(28),
        highway_mpg=Decimal(39),
        combined_mpg=Decimal(32),
        fuel_grade=GasolineGrade.PREMIUM,
    )

    assert specification.city_mpg == Decimal(28)
    assert specification.highway_mpg == Decimal(39)
    assert specification.combined_mpg == Decimal(32)
    assert specification.fuel_grade is GasolineGrade.PREMIUM


def test_gasoline_vehicle_specification_rejects_zero_combined_mpg() -> None:
    with pytest.raises(
        ValueError,
        match="combined_mpg must be greater than zero",
    ):
        GasolineVehicleSpecification(
            combined_mpg=Decimal(0),
            fuel_grade=GasolineGrade.REGULAR,
        )


def test_gasoline_vehicle_specification_rejects_negative_combined_mpg() -> None:
    with pytest.raises(
        ValueError,
        match="combined_mpg must be greater than zero",
    ):
        GasolineVehicleSpecification(
            combined_mpg=Decimal(-1),
            fuel_grade=GasolineGrade.REGULAR,
        )


@pytest.mark.parametrize(
    "city_mpg",
    [
        Decimal(0),
        Decimal(-1),
    ],
)
def test_gasoline_vehicle_specification_rejects_nonpositive_city_mpg(
    city_mpg: Decimal,
) -> None:
    with pytest.raises(
        ValueError,
        match="city_mpg must be greater than zero when provided",
    ):
        GasolineVehicleSpecification(
            city_mpg=city_mpg,
            highway_mpg=Decimal(39),
            combined_mpg=Decimal(32),
            fuel_grade=GasolineGrade.REGULAR,
        )


@pytest.mark.parametrize(
    "highway_mpg",
    [
        Decimal(0),
        Decimal(-1),
    ],
)
def test_gasoline_vehicle_specification_rejects_nonpositive_highway_mpg(
    highway_mpg: Decimal,
) -> None:
    with pytest.raises(
        ValueError,
        match="highway_mpg must be greater than zero when provided",
    ):
        GasolineVehicleSpecification(
            city_mpg=Decimal(28),
            highway_mpg=highway_mpg,
            combined_mpg=Decimal(32),
            fuel_grade=GasolineGrade.REGULAR,
        )


def test_electric_vehicle_specification_accepts_valid_values() -> None:
    specification = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.285"),
    )

    assert specification.combined_kwh_per_mile == Decimal("0.285")


def test_electric_vehicle_specification_rejects_zero_efficiency() -> None:
    with pytest.raises(
        ValueError,
        match="combined_kwh_per_mile must be greater than zero",
    ):
        ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal(0),
        )


def test_electric_vehicle_specification_rejects_negative_efficiency() -> None:
    with pytest.raises(
        ValueError,
        match="combined_kwh_per_mile must be greater than zero",
    ):
        ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("-0.001"),
        )
