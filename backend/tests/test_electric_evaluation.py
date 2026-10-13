"""Tests for electric evaluation using durable saved BEV snapshots."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from routevalue.application.electric_evaluation import (
    UnsupportedElectricVehicleEnergyTypeError,
    build_electric_evaluation_context,
)
from routevalue.application.models import VehicleCatalogConfiguration
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.domain.identity import SavedVehicleId
from routevalue.domain.models import (
    ElectricConsumption,
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
    VehicleEnergySpecification,
)
from routevalue.infrastructure.energy.electric import (
    ElectricEnergyCostEstimator,
)


def _saved_vehicle(
    specification: VehicleEnergySpecification,
) -> SavedVehicle:
    return SavedVehicle(
        id=SavedVehicleId(value=uuid4()),
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Hyundai",
            model="Ioniq 5",
            configuration="Long Range RWD",
            source="fueleconomy_gov",
            source_id="12345",
        ),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 1, tzinfo=UTC),
        saved_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


def _bev() -> SavedVehicle:
    return _saved_vehicle(
        ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.285"),
            city_kwh_per_mile=Decimal("0.250"),
            highway_kwh_per_mile=Decimal("0.320"),
        )
    )


def _route() -> RouteCandidate:
    return RouteCandidate(
        distance_meters=201_168,
        duration_seconds=3600,
        toll_cost=Decimal(0),
    )


def test_context_uses_persisted_combined_efficiency() -> None:
    """Combined efficiency must come from the saved BEV snapshot."""

    saved = _bev()

    context = build_electric_evaluation_context(
        saved,
        price_per_kilowatt_hour=Decimal("0.3125"),
    )

    assert context.vehicle is saved.specification

    assert context.vehicle.combined_kwh_per_mile == Decimal("0.285")
    assert context.vehicle.city_kwh_per_mile == Decimal("0.250")
    assert context.vehicle.highway_kwh_per_mile == Decimal("0.320")

    assert context.electricity_price_quote.price_per_kilowatt_hour == Decimal("0.3125")


def test_saved_bev_context_integrates_with_electric_estimator() -> None:
    context = build_electric_evaluation_context(
        _bev(),
        price_per_kilowatt_hour=Decimal("0.3125"),
    )

    estimator = ElectricEnergyCostEstimator(
        vehicle=context.vehicle,
        electricity_price_quote=context.electricity_price_quote,
    )

    estimate = estimator.estimate_energy(_route())

    assert estimate is not None
    assert isinstance(estimate.consumption, ElectricConsumption)

    # 125 miles * 0.285 kWh/mile = 35.625 kWh.
    expected_kwh = Decimal("35.625")
    expected_cost = expected_kwh * Decimal("0.3125")

    assert estimate.consumption.kilowatt_hours == expected_kwh
    assert estimate.cost == expected_cost


def test_context_accepts_zero_electricity_price() -> None:
    context = build_electric_evaluation_context(
        _bev(),
        price_per_kilowatt_hour=Decimal(0),
    )

    estimator = ElectricEnergyCostEstimator(
        vehicle=context.vehicle,
        electricity_price_quote=context.electricity_price_quote,
    )

    estimate = estimator.estimate_energy(_route())

    assert estimate is not None
    assert estimate.cost == Decimal(0)

    assert isinstance(estimate.consumption, ElectricConsumption)
    assert estimate.consumption.kilowatt_hours > 0


@pytest.mark.parametrize(
    "invalid_price",
    [
        Decimal("-0.01"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_context_rejects_invalid_electricity_prices(
    invalid_price: Decimal,
) -> None:
    with pytest.raises(ValueError):
        build_electric_evaluation_context(
            _bev(),
            price_per_kilowatt_hour=invalid_price,
        )


def test_gasoline_vehicle_cannot_enter_electric_context() -> None:
    gasoline = _saved_vehicle(
        GasolineVehicleSpecification(
            combined_mpg=Decimal(30),
            fuel_grade=GasolineGrade.REGULAR,
        )
    )

    with pytest.raises(UnsupportedElectricVehicleEnergyTypeError):
        build_electric_evaluation_context(
            gasoline,
            price_per_kilowatt_hour=Decimal("0.31"),
        )


def test_context_creation_does_not_modify_saved_snapshot() -> None:
    saved = _bev()

    original_specification = saved.specification
    original_retrieved_at = saved.specification_retrieved_at
    original_saved_at = saved.saved_at

    context = build_electric_evaluation_context(
        saved,
        price_per_kilowatt_hour=Decimal("0.31"),
    )

    assert saved.specification is original_specification
    assert saved.specification_retrieved_at == original_retrieved_at
    assert saved.saved_at == original_saved_at

    assert context.vehicle is original_specification
