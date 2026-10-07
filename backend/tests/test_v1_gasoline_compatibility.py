from decimal import Decimal

from routevalue.domain.decision_engine import (
    calculate_cost_breakdown,
    calculate_generalized_cost,
    decide_route,
)
from routevalue.domain.gasoline_energy import estimate_gasoline_energy
from routevalue.domain.models import (
    DecisionCandidate,
    DecisionReason,
    FuelPriceQuote,
    FuelPriceSource,
    GasolineGrade,
    GasolineVehicleProfile,
    RouteCandidate,
)


def test_v1_gasoline_generalized_cost_regression() -> None:
    route = RouteCandidate(
        distance_meters=201_168,
        duration_seconds=7_200,
        toll_cost=Decimal("5.00"),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal("4.00"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    energy_estimate = estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price,
    )
    candidate = DecisionCandidate(
        route=route,
        energy_estimate=energy_estimate,
    )

    breakdown = calculate_cost_breakdown(
        candidate,
        value_of_time_per_hour=Decimal("20.00"),
    )

    assert energy_estimate.cost == Decimal("20.00")
    assert breakdown.monetary_cost == Decimal("25.00")
    assert breakdown.time_cost == Decimal("40.00")
    assert breakdown.generalized_cost == Decimal("65.00")


def test_v1_gasoline_route_selection_regression_on_exact_cost_tie() -> None:
    slower_shorter_route = RouteCandidate(
        distance_meters=201_168,
        duration_seconds=7_200,
        toll_cost=Decimal("0.00"),
    )
    faster_longer_route = RouteCandidate(
        distance_meters=402_336,
        duration_seconds=3_600,
        toll_cost=Decimal("0.00"),
    )

    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal("4.00"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    slower_shorter_candidate = DecisionCandidate(
        route=slower_shorter_route,
        energy_estimate=estimate_gasoline_energy(
            slower_shorter_route,
            vehicle=vehicle,
            fuel_price_quote=fuel_price,
        ),
    )
    faster_longer_candidate = DecisionCandidate(
        route=faster_longer_route,
        energy_estimate=estimate_gasoline_energy(
            faster_longer_route,
            vehicle=vehicle,
            fuel_price_quote=fuel_price,
        ),
    )

    slower_shorter_cost = calculate_generalized_cost(
        slower_shorter_candidate,
        value_of_time_per_hour=Decimal("20.00"),
    )
    faster_longer_cost = calculate_generalized_cost(
        faster_longer_candidate,
        value_of_time_per_hour=Decimal("20.00"),
    )

    result = decide_route(
        [slower_shorter_candidate, faster_longer_candidate],
        value_of_time_per_hour=Decimal("20.00"),
        candidate_count=2,
        missing_data_present=False,
    )

    assert slower_shorter_candidate.energy_estimate.cost == Decimal("20.00")
    assert faster_longer_candidate.energy_estimate.cost == Decimal("40.00")

    assert slower_shorter_cost == Decimal("60.00")
    assert faster_longer_cost == Decimal("60.00")

    assert result.recommended_route is faster_longer_route
    assert result.reason is DecisionReason.NUMERICAL_TIE_FASTER_WINS
    assert result.numerical_tie is True
    assert result.missing_data_present is False
    assert result.candidate_count == 2
    assert result.eligible_count == 2
