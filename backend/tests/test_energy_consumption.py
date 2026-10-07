from decimal import Decimal

import pytest

from routevalue.domain.models import (
    ElectricConsumption,
    GasolineConsumption,
)


def test_gasoline_consumption_accepts_positive_gallons() -> None:
    consumption = GasolineConsumption(
        gallons=Decimal("3.75"),
    )

    assert consumption.gallons == Decimal("3.75")


def test_gasoline_consumption_allows_zero_gallons() -> None:
    consumption = GasolineConsumption(
        gallons=Decimal(0),
    )

    assert consumption.gallons == Decimal(0)


def test_gasoline_consumption_rejects_negative_gallons() -> None:
    with pytest.raises(
        ValueError,
        match="gallons cannot be negative",
    ):
        GasolineConsumption(
            gallons=Decimal("-0.01"),
        )


def test_electric_consumption_accepts_positive_kilowatt_hours() -> None:
    consumption = ElectricConsumption(
        kilowatt_hours=Decimal("18.25"),
    )

    assert consumption.kilowatt_hours == Decimal("18.25")


def test_electric_consumption_allows_zero_kilowatt_hours() -> None:
    consumption = ElectricConsumption(
        kilowatt_hours=Decimal(0),
    )

    assert consumption.kilowatt_hours == Decimal(0)


def test_electric_consumption_rejects_negative_kilowatt_hours() -> None:
    with pytest.raises(
        ValueError,
        match="kilowatt_hours cannot be negative",
    ):
        ElectricConsumption(
            kilowatt_hours=Decimal("-0.01"),
        )
