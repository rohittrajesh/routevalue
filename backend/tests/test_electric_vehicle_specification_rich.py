from decimal import Decimal

import pytest

from routevalue.domain.models import ElectricVehicleSpecification


def test_electric_vehicle_specification_preserves_combined_only_compatibility() -> None:
    specification = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.285"),
    )

    assert specification.combined_kwh_per_mile == Decimal("0.285")
    assert specification.city_kwh_per_mile is None
    assert specification.highway_kwh_per_mile is None


def test_electric_vehicle_specification_accepts_city_highway_and_combined_values() -> None:
    specification = ElectricVehicleSpecification(
        city_kwh_per_mile=Decimal("0.260"),
        highway_kwh_per_mile=Decimal("0.310"),
        combined_kwh_per_mile=Decimal("0.285"),
    )

    assert specification.city_kwh_per_mile == Decimal("0.260")
    assert specification.highway_kwh_per_mile == Decimal("0.310")
    assert specification.combined_kwh_per_mile == Decimal("0.285")


@pytest.mark.parametrize(
    "city_kwh_per_mile",
    [
        Decimal(0),
        Decimal("-0.001"),
    ],
)
def test_electric_vehicle_specification_rejects_nonpositive_city_efficiency(
    city_kwh_per_mile: Decimal,
) -> None:
    with pytest.raises(
        ValueError,
        match="city_kwh_per_mile must be greater than zero when provided",
    ):
        ElectricVehicleSpecification(
            city_kwh_per_mile=city_kwh_per_mile,
            highway_kwh_per_mile=Decimal("0.310"),
            combined_kwh_per_mile=Decimal("0.285"),
        )


@pytest.mark.parametrize(
    "highway_kwh_per_mile",
    [
        Decimal(0),
        Decimal("-0.001"),
    ],
)
def test_electric_vehicle_specification_rejects_nonpositive_highway_efficiency(
    highway_kwh_per_mile: Decimal,
) -> None:
    with pytest.raises(
        ValueError,
        match="highway_kwh_per_mile must be greater than zero when provided",
    ):
        ElectricVehicleSpecification(
            city_kwh_per_mile=Decimal("0.260"),
            highway_kwh_per_mile=highway_kwh_per_mile,
            combined_kwh_per_mile=Decimal("0.285"),
        )
