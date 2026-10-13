"""Tests for gasoline evaluation using durable saved vehicle snapshots."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from routevalue.application.gasoline_evaluation import (
    UnsupportedVehicleEnergyTypeError,
    build_gasoline_evaluation_context,
)
from routevalue.application.models import VehicleCatalogConfiguration
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.domain.identity import SavedVehicleId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineConsumption,
    GasolineGrade,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    RouteCandidate,
    VehicleEnergySpecification,
)
from routevalue.infrastructure.energy.gasoline import (
    GasolineEnergyCostEstimator,
)


def _saved_vehicle(
    specification: VehicleEnergySpecification,
) -> SavedVehicle:
    """Create a durable normalized vehicle snapshot."""

    return SavedVehicle(
        id=SavedVehicleId(value=uuid4()),
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Toyota",
            model="Camry",
            configuration="2.5L 4cyl CVT (FWD)",
            source="fueleconomy_gov",
            source_id="12345",
        ),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 1, tzinfo=UTC),
        saved_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


def _gasoline_vehicle(
    grade: GasolineGrade = GasolineGrade.REGULAR,
) -> SavedVehicle:
    return _saved_vehicle(
        GasolineVehicleSpecification(
            combined_mpg=Decimal("32.125"),
            city_mpg=Decimal("28.5"),
            highway_mpg=Decimal("38.25"),
            fuel_grade=grade,
        )
    )


def _route(
    distance_meters: int = 1_609_344,
) -> RouteCandidate:
    return RouteCandidate(
        distance_meters=distance_meters,
        duration_seconds=3600,
        toll_cost=Decimal(0),
    )


@pytest.mark.parametrize(
    "grade",
    [
        GasolineGrade.REGULAR,
        GasolineGrade.MIDGRADE,
        GasolineGrade.PREMIUM,
    ],
)
def test_context_uses_persisted_mpg_and_gasoline_grade(
    grade: GasolineGrade,
) -> None:
    """Neither MPG nor fuel grade comes from client overrides."""

    saved = _gasoline_vehicle(grade)

    context = build_gasoline_evaluation_context(
        saved,
        fuel_price_per_gallon=Decimal("4.590125"),
    )

    assert context.vehicle.fuel_efficiency_mpg == Decimal("32.125")
    assert context.vehicle.fuel_grade is grade

    assert context.fuel_price_quote.fuel_grade is grade
    assert context.fuel_price_quote.price_per_gallon == Decimal("4.590125")

    assert context.fuel_price_quote.source is (GasolinePriceSource.USER_OVERRIDE)
    assert context.fuel_price_quote.observed_at is None


def test_context_integrates_with_existing_gasoline_estimator() -> None:
    """M4 must reuse the baseline energy calculation and Decimal math."""

    context = build_gasoline_evaluation_context(
        _gasoline_vehicle(GasolineGrade.PREMIUM),
        fuel_price_per_gallon=Decimal("4.590125"),
    )

    estimator = GasolineEnergyCostEstimator(
        vehicle=context.vehicle,
        fuel_price_quote=context.fuel_price_quote,
    )

    estimate = estimator.estimate_energy(_route())

    assert estimate is not None

    assert isinstance(estimate.consumption, GasolineConsumption)

    expected_gallons = Decimal(1000) / Decimal("32.125")
    expected_cost = expected_gallons * Decimal("4.590125")

    assert estimate.consumption.gallons == expected_gallons
    assert estimate.cost == expected_cost


def test_zero_distance_preserves_zero_consumption() -> None:
    """The existing energy model must still handle zero distance."""

    context = build_gasoline_evaluation_context(
        _gasoline_vehicle(),
        fuel_price_per_gallon=Decimal("4.59"),
    )

    estimator = GasolineEnergyCostEstimator(
        vehicle=context.vehicle,
        fuel_price_quote=context.fuel_price_quote,
    )

    estimate = estimator.estimate_energy(_route(distance_meters=0))

    assert estimate is not None
    assert estimate.cost == Decimal(0)
    assert estimate.consumption == GasolineConsumption(gallons=Decimal(0))


def test_zero_gasoline_price_is_valid() -> None:
    """Zero is known pricing information, not a missing quote."""

    context = build_gasoline_evaluation_context(
        _gasoline_vehicle(),
        fuel_price_per_gallon=Decimal(0),
    )

    estimator = GasolineEnergyCostEstimator(
        vehicle=context.vehicle,
        fuel_price_quote=context.fuel_price_quote,
    )

    estimate = estimator.estimate_energy(_route())

    assert estimate is not None
    assert estimate.cost == Decimal(0)

    assert isinstance(estimate.consumption, GasolineConsumption)
    assert estimate.consumption.gallons > 0


@pytest.mark.parametrize(
    "invalid_price",
    [
        Decimal("-0.01"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_context_rejects_invalid_prices(
    invalid_price: Decimal,
) -> None:
    """Application code must reject invalid prices without relying on HTTP."""

    with pytest.raises(ValueError):
        build_gasoline_evaluation_context(
            _gasoline_vehicle(),
            fuel_price_per_gallon=invalid_price,
        )


def test_bev_is_explicitly_unsupported_in_m4() -> None:
    """Resolving a BEV profile must not trigger gasoline evaluation."""

    bev = _saved_vehicle(
        ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.285"),
            city_kwh_per_mile=Decimal("0.250"),
            highway_kwh_per_mile=Decimal("0.320"),
        )
    )

    with pytest.raises(UnsupportedVehicleEnergyTypeError):
        build_gasoline_evaluation_context(
            bev,
            fuel_price_per_gallon=Decimal("4.59"),
        )


def test_context_creation_does_not_modify_saved_snapshot() -> None:
    """Using a saved specification must not mutate durable vehicle state."""

    saved = _gasoline_vehicle(GasolineGrade.PREMIUM)

    original_specification = saved.specification
    original_retrieved_at = saved.specification_retrieved_at
    original_saved_at = saved.saved_at

    first = build_gasoline_evaluation_context(
        saved,
        fuel_price_per_gallon=Decimal("4.59"),
    )

    second = build_gasoline_evaluation_context(
        saved,
        fuel_price_per_gallon=Decimal("4.59"),
    )

    assert first == second

    assert saved.specification is original_specification
    assert saved.specification_retrieved_at == original_retrieved_at
    assert saved.saved_at == original_saved_at
