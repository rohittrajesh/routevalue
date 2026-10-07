from decimal import Decimal

import pytest

from routevalue.domain.decision_engine import calculate_generalized_cost
from routevalue.domain.models import (
    DecisionCandidate,
    ElectricConsumption,
    EnergyEstimate,
    GasolineConsumption,
    RouteCandidate,
)


def test_energy_estimate_accepts_gasoline_consumption() -> None:
    consumption = GasolineConsumption(
        gallons=Decimal("4.25"),
    )

    estimate = EnergyEstimate(
        cost=Decimal("18.70"),
        consumption=consumption,
    )

    assert estimate.cost == Decimal("18.70")
    assert estimate.consumption is consumption


def test_energy_estimate_accepts_electric_consumption() -> None:
    consumption = ElectricConsumption(
        kilowatt_hours=Decimal("21.5"),
    )

    estimate = EnergyEstimate(
        cost=Decimal("6.45"),
        consumption=consumption,
    )

    assert estimate.cost == Decimal("6.45")
    assert estimate.consumption is consumption


def test_energy_estimate_preserves_legacy_cost_only_construction() -> None:
    estimate = EnergyEstimate(
        cost=Decimal("12.50"),
    )

    assert estimate.cost == Decimal("12.50")
    assert estimate.consumption is None


def test_energy_estimate_allows_zero_cost_with_consumption() -> None:
    consumption = ElectricConsumption(
        kilowatt_hours=Decimal("5.00"),
    )

    estimate = EnergyEstimate(
        cost=Decimal(0),
        consumption=consumption,
    )

    assert estimate.cost == Decimal(0)
    assert estimate.consumption is consumption


def test_energy_estimate_rejects_negative_cost_with_consumption() -> None:
    consumption = GasolineConsumption(
        gallons=Decimal("1.00"),
    )

    with pytest.raises(
        ValueError,
        match="energy cost cannot be negative",
    ):
        EnergyEstimate(
            cost=Decimal("-0.01"),
            consumption=consumption,
        )


def test_decision_engine_uses_cost_boundary_with_physical_consumption() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_800,
        toll_cost=Decimal("3.00"),
    )
    estimate = EnergyEstimate(
        cost=Decimal("4.00"),
        consumption=GasolineConsumption(
            gallons=Decimal("1.00"),
        ),
    )
    candidate = DecisionCandidate(
        route=route,
        energy_estimate=estimate,
    )

    result = calculate_generalized_cost(
        candidate,
        value_of_time_per_hour=Decimal("20.00"),
    )

    assert result == Decimal("17.00")
