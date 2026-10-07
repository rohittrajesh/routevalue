from decimal import Decimal

from routevalue.domain.decision_engine import calculate_generalized_cost
from routevalue.domain.models import (
    DecisionCandidate,
    ElectricConsumption,
    EnergyEstimate,
    GasolineConsumption,
    RouteCandidate,
)


def test_gasoline_and_electric_consumption_remain_distinct_domain_concepts() -> None:
    gasoline = GasolineConsumption(
        gallons=Decimal(5),
    )
    electric = ElectricConsumption(
        kilowatt_hours=Decimal(5),
    )

    gasoline_estimate = EnergyEstimate(
        cost=Decimal("10.00"),
        consumption=gasoline,
    )
    electric_estimate = EnergyEstimate(
        cost=Decimal("10.00"),
        consumption=electric,
    )

    assert isinstance(
        gasoline_estimate.consumption,
        GasolineConsumption,
    )
    assert isinstance(
        electric_estimate.consumption,
        ElectricConsumption,
    )

    assert gasoline_estimate.consumption.gallons == Decimal(5)
    assert electric_estimate.consumption.kilowatt_hours == Decimal(5)


def test_decision_scoring_is_independent_of_physical_energy_type() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_800,
        toll_cost=Decimal("3.00"),
    )

    gasoline_candidate = DecisionCandidate(
        route=route,
        energy_estimate=EnergyEstimate(
            cost=Decimal("4.00"),
            consumption=GasolineConsumption(
                gallons=Decimal("1.00"),
            ),
        ),
    )
    electric_candidate = DecisionCandidate(
        route=route,
        energy_estimate=EnergyEstimate(
            cost=Decimal("4.00"),
            consumption=ElectricConsumption(
                kilowatt_hours=Decimal("12.00"),
            ),
        ),
    )

    gasoline_cost = calculate_generalized_cost(
        gasoline_candidate,
        value_of_time_per_hour=Decimal("20.00"),
    )
    electric_cost = calculate_generalized_cost(
        electric_candidate,
        value_of_time_per_hour=Decimal("20.00"),
    )

    assert gasoline_cost == Decimal("17.00")
    assert electric_cost == Decimal("17.00")
    assert gasoline_cost == electric_cost
