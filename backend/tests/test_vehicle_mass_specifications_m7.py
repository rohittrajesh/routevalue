"""M7-B2-B tests for vehicle-mass-aware specifications."""

from decimal import Decimal

import pytest

from routevalue.domain.energy_consumption import (
    estimate_baseline_electric_consumption,
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


def _mass() -> VehicleMass:
    return VehicleMass(
        kilograms=Decimal(1750),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        source_reference="manufacturer-test-record",
    )


def _route() -> RouteCandidate:
    return RouteCandidate(
        distance_meters=160_934,
        duration_seconds=7200,
        toll_cost=Decimal(0),
    )


def test_gasoline_specification_accepts_vehicle_mass() -> None:
    mass = _mass()
    vehicle = GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=mass,
    )

    assert vehicle.vehicle_mass == mass
    assert vehicle.vehicle_mass.source is VehicleMassSource.MANUFACTURER_CURB_WEIGHT


def test_electric_specification_accepts_vehicle_mass() -> None:
    mass = _mass()
    vehicle = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=mass,
    )

    assert vehicle.vehicle_mass == mass


def test_existing_gasoline_constructor_defaults_to_missing_mass() -> None:
    vehicle = GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )

    assert vehicle.vehicle_mass is None


def test_existing_electric_constructor_defaults_to_missing_mass() -> None:
    vehicle = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
    )

    assert vehicle.vehicle_mass is None


def test_gasoline_baseline_is_unchanged_by_vehicle_mass() -> None:
    without_mass = GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )
    with_mass = GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=_mass(),
    )

    assert estimate_baseline_gasoline_consumption(
        _route(), vehicle=without_mass
    ) == estimate_baseline_gasoline_consumption(_route(), vehicle=with_mass)


def test_electric_baseline_is_unchanged_by_vehicle_mass() -> None:
    without_mass = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
    )
    with_mass = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=_mass(),
    )

    assert estimate_baseline_electric_consumption(
        _route(), vehicle=without_mass
    ) == estimate_baseline_electric_consumption(_route(), vehicle=with_mass)


@pytest.mark.parametrize(
    "invalid_mass",
    [
        Decimal(1750),
        "1750",
        1750,
        -1,
    ],
)
def test_gasoline_specification_rejects_invalid_mass_type(
    invalid_mass: object,
) -> None:
    with pytest.raises(TypeError):
        GasolineVehicleSpecification(
            combined_mpg=Decimal(30),
            fuel_grade=GasolineGrade.REGULAR,
            vehicle_mass=invalid_mass,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "invalid_mass",
    [
        Decimal(1750),
        "1750",
        1750,
        -1,
    ],
)
def test_electric_specification_rejects_invalid_mass_type(
    invalid_mass: object,
) -> None:
    with pytest.raises(TypeError):
        ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.30"),
            vehicle_mass=invalid_mass,  # type: ignore[arg-type]
        )
