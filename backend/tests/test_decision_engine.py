from decimal import Decimal

import pytest

from routevalue.domain.decision_engine import (
    calculate_cost_breakdown,
    calculate_generalized_cost,
    calculate_monetary_cost,
    calculate_time_cost,
    decide_route,
    is_numerical_tie,
    resolve_numerical_tie,
    select_lowest_generalized_cost_candidate,
)
from routevalue.domain.models import (
    DecisionCandidate,
    DecisionReason,
    EnergyEstimate,
    RouteCandidate,
)


def test_calculate_monetary_cost_adds_toll_and_energy_cost() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_800,
        toll_cost=Decimal("3.50"),
    )
    energy_estimate = EnergyEstimate(cost=Decimal("4.25"))
    candidate = DecisionCandidate(
        route=route,
        energy_estimate=energy_estimate,
    )

    result = calculate_monetary_cost(candidate)

    assert result == Decimal("7.75")


def test_calculate_time_cost_converts_seconds_to_hours() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_800,
        toll_cost=Decimal(0),
    )

    result = calculate_time_cost(
        route,
        value_of_time_per_hour=Decimal("20.00"),
    )

    assert result == Decimal("10.00")


def test_calculate_time_cost_allows_zero_value_of_time() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_800,
        toll_cost=Decimal(0),
    )

    result = calculate_time_cost(
        route,
        value_of_time_per_hour=Decimal(0),
    )

    assert result == Decimal(0)


def test_calculate_time_cost_rejects_negative_value_of_time() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_800,
        toll_cost=Decimal(0),
    )

    with pytest.raises(
        ValueError,
        match="value_of_time_per_hour cannot be negative",
    ):
        calculate_time_cost(
            route,
            value_of_time_per_hour=Decimal("-1.00"),
        )


def test_calculate_generalized_cost_combines_all_components() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_800,
        toll_cost=Decimal("3.00"),
    )
    energy_estimate = EnergyEstimate(cost=Decimal("4.00"))
    candidate = DecisionCandidate(
        route=route,
        energy_estimate=energy_estimate,
    )

    result = calculate_generalized_cost(
        candidate,
        value_of_time_per_hour=Decimal("20.00"),
    )

    assert result == Decimal("17.00")


def test_decide_route_returns_no_recommendation_when_none_are_eligible() -> None:
    result = decide_route(
        [],
        value_of_time_per_hour=Decimal("20.00"),
        candidate_count=2,
        missing_data_present=True,
    )

    assert result.recommended_route is None
    assert result.reason is None
    assert result.numerical_tie is False
    assert result.missing_data_present is True
    assert result.candidate_count == 2
    assert result.eligible_count == 0


def test_decide_route_selects_only_eligible_candidate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_800,
        toll_cost=Decimal("3.00"),
    )
    candidate = DecisionCandidate(
        route=route,
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )

    result = decide_route(
        [candidate],
        value_of_time_per_hour=Decimal("20.00"),
        candidate_count=2,
        missing_data_present=True,
    )

    assert result.recommended_route is route
    assert result.reason is DecisionReason.ONLY_ELIGIBLE_ROUTE
    assert result.numerical_tie is False
    assert result.missing_data_present is True
    assert result.candidate_count == 2
    assert result.eligible_count == 1


def test_decide_route_selects_cheaper_route_worth_extra_time() -> None:
    cheaper_slower = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("1.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )
    faster_costlier = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_200,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )

    result = decide_route(
        [cheaper_slower, faster_costlier],
        value_of_time_per_hour=Decimal("20.00"),
        candidate_count=2,
        missing_data_present=False,
    )

    assert result.recommended_route is cheaper_slower.route
    assert result.reason is DecisionReason.CHEAPER_ROUTE_WORTH_EXTRA_TIME
    assert result.numerical_tie is False
    assert result.candidate_count == 2
    assert result.eligible_count == 2


def test_select_lowest_generalized_cost_can_choose_cheaper_slower_route() -> None:
    cheaper_slower = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("1.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )
    faster_costlier = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_200,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )

    result = select_lowest_generalized_cost_candidate(
        [cheaper_slower, faster_costlier],
        value_of_time_per_hour=Decimal("20.00"),
    )

    assert result is cheaper_slower


def test_select_lowest_generalized_cost_can_choose_faster_costlier_route() -> None:
    slower_cheaper = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("1.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )
    faster_costlier = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_200,
            toll_cost=Decimal("3.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )

    result = select_lowest_generalized_cost_candidate(
        [slower_cheaper, faster_costlier],
        value_of_time_per_hour=Decimal("20.00"),
    )

    assert result is faster_costlier


def test_select_lowest_generalized_cost_supports_multiple_candidates() -> None:
    first = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("4.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )
    second = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=11_000,
            duration_seconds=1_500,
            toll_cost=Decimal("2.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )
    third = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=12_000,
            duration_seconds=1_200,
            toll_cost=Decimal("6.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )

    result = select_lowest_generalized_cost_candidate(
        [first, second, third],
        value_of_time_per_hour=Decimal("20.00"),
    )

    assert result is second


def test_select_lowest_generalized_cost_resolves_exact_tie() -> None:
    shorter = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("2.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("3.00")),
    )
    longer = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=12_000,
            duration_seconds=1_800,
            toll_cost=Decimal("2.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("3.00")),
    )

    result = select_lowest_generalized_cost_candidate(
        [longer, shorter],
        value_of_time_per_hour=Decimal("20.00"),
    )

    assert result is shorter


def test_is_numerical_tie_below_tolerance() -> None:
    assert is_numerical_tie(
        Decimal("10.00"),
        Decimal("10.09"),
    )


def test_is_numerical_tie_at_tolerance_is_not_tie() -> None:
    assert not is_numerical_tie(
        Decimal("10.00"),
        Decimal("10.10"),
    )


def test_is_numerical_tie_above_tolerance_is_not_tie() -> None:
    assert not is_numerical_tie(
        Decimal("10.00"),
        Decimal("10.11"),
    )


def test_select_lowest_generalized_cost_resolves_numerical_tie() -> None:
    lower_cost = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    faster_near_tie = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=11_000,
            duration_seconds=1_700,
            toll_cost=Decimal("5.09"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )

    result = select_lowest_generalized_cost_candidate(
        [lower_cost, faster_near_tie],
        value_of_time_per_hour=Decimal(0),
    )

    assert result is faster_near_tie


def test_select_lowest_generalized_cost_selects_lower_cost_at_tolerance() -> None:
    lower_cost = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    higher_cost = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=11_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.10"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )

    result = select_lowest_generalized_cost_candidate(
        [lower_cost, higher_cost],
        value_of_time_per_hour=Decimal(0),
    )

    assert result is lower_cost


def test_resolve_numerical_tie_prefers_faster_route() -> None:
    slower_cheaper = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    faster_costlier = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=11_000,
            duration_seconds=1_700,
            toll_cost=Decimal("5.09"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )

    result = resolve_numerical_tie([slower_cheaper, faster_costlier])

    assert result is faster_costlier


def test_resolve_numerical_tie_prefers_lower_monetary_cost() -> None:
    cheaper = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=11_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    costlier = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.09"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )

    result = resolve_numerical_tie([costlier, cheaper])

    assert result is cheaper


def test_resolve_numerical_tie_prefers_shorter_distance() -> None:
    longer = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=12_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    shorter = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )

    result = resolve_numerical_tie([longer, shorter])

    assert result is shorter


def test_resolve_numerical_tie_preserves_input_order_as_final_fallback() -> None:
    first = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("2.00")),
    )
    second = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("2.00")),
    )

    result = resolve_numerical_tie([first, second])

    assert result is first


def test_decide_route_selects_faster_route_worth_extra_cost() -> None:
    slower_cheaper = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("1.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )
    faster_costlier = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_200,
            toll_cost=Decimal("3.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )

    result = decide_route(
        [slower_cheaper, faster_costlier],
        value_of_time_per_hour=Decimal("20.00"),
        candidate_count=2,
        missing_data_present=False,
    )

    assert result.recommended_route is faster_costlier.route
    assert result.reason is DecisionReason.FASTER_ROUTE_WORTH_EXTRA_COST
    assert result.numerical_tie is False


def test_decide_route_selects_faster_and_cheaper_route() -> None:
    worse_route = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=12_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )
    better_route = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_200,
            toll_cost=Decimal("2.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )

    result = decide_route(
        [worse_route, better_route],
        value_of_time_per_hour=Decimal("20.00"),
        candidate_count=2,
        missing_data_present=False,
    )

    assert result.recommended_route is better_route.route
    assert result.reason is DecisionReason.FASTER_AND_CHEAPER
    assert result.numerical_tie is False


def test_decide_route_reports_numerical_tie_faster_wins() -> None:
    slower = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    faster = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=11_000,
            duration_seconds=1_700,
            toll_cost=Decimal("5.09"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )

    result = decide_route(
        [slower, faster],
        value_of_time_per_hour=Decimal(0),
        candidate_count=2,
        missing_data_present=False,
    )

    assert result.recommended_route is faster.route
    assert result.reason is DecisionReason.NUMERICAL_TIE_FASTER_WINS
    assert result.numerical_tie is True


def test_decide_route_reports_numerical_tie_cheaper_wins() -> None:
    costlier = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.09"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    cheaper = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=11_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )

    result = decide_route(
        [costlier, cheaper],
        value_of_time_per_hour=Decimal(0),
        candidate_count=2,
        missing_data_present=False,
    )

    assert result.recommended_route is cheaper.route
    assert result.reason is DecisionReason.NUMERICAL_TIE_CHEAPER_WINS
    assert result.numerical_tie is True


def test_decide_route_reports_numerical_tie_shorter_distance_wins() -> None:
    longer = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=12_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    shorter = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )

    result = decide_route(
        [longer, shorter],
        value_of_time_per_hour=Decimal(0),
        candidate_count=2,
        missing_data_present=False,
    )

    assert result.recommended_route is shorter.route
    assert result.reason is DecisionReason.NUMERICAL_TIE_SHORTER_DISTANCE_WINS
    assert result.numerical_tie is True


def test_decide_route_reports_stable_order_as_final_tie_break() -> None:
    first = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("2.00")),
    )
    second = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("2.00")),
    )

    result = decide_route(
        [first, second],
        value_of_time_per_hour=Decimal("20.00"),
        candidate_count=2,
        missing_data_present=False,
    )

    assert result.recommended_route is first.route
    assert result.reason is DecisionReason.NUMERICAL_TIE_STABLE_ORDER_WINS
    assert result.numerical_tie is True


def test_decide_route_handles_three_eligible_candidates() -> None:
    slow_cheap = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("1.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )
    balanced = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=11_000,
            duration_seconds=1_500,
            toll_cost=Decimal("2.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )
    fast_expensive = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=12_000,
            duration_seconds=1_200,
            toll_cost=Decimal("7.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )

    result = decide_route(
        [slow_cheap, balanced, fast_expensive],
        value_of_time_per_hour=Decimal("20.00"),
        candidate_count=3,
        missing_data_present=False,
    )

    assert result.recommended_route is balanced.route
    assert result.reason is DecisionReason.FASTER_ROUTE_WORTH_EXTRA_COST
    assert result.numerical_tie is False
    assert result.candidate_count == 3
    assert result.eligible_count == 3


def test_numerical_tie_set_is_anchored_to_lowest_generalized_cost() -> None:
    lowest = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("10.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    near_lowest = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=11_000,
            duration_seconds=1_700,
            toll_cost=Decimal("10.09"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    chained_but_not_tied_to_minimum = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=12_000,
            duration_seconds=1_000,
            toll_cost=Decimal("10.18"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )

    result = decide_route(
        [
            lowest,
            near_lowest,
            chained_but_not_tied_to_minimum,
        ],
        value_of_time_per_hour=Decimal(0),
        candidate_count=3,
        missing_data_present=False,
    )

    assert result.recommended_route is near_lowest.route
    assert result.reason is DecisionReason.NUMERICAL_TIE_FASTER_WINS
    assert result.numerical_tie is True


def test_decide_route_does_not_treat_exact_tolerance_as_numerical_tie() -> None:
    cheaper_slower = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )
    faster_costlier = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=11_000,
            duration_seconds=1_200,
            toll_cost=Decimal("5.10"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal(0)),
    )

    result = decide_route(
        [cheaper_slower, faster_costlier],
        value_of_time_per_hour=Decimal(0),
        candidate_count=2,
        missing_data_present=False,
    )

    assert result.recommended_route is cheaper_slower.route
    assert result.reason is DecisionReason.CHEAPER_ROUTE_WORTH_EXTRA_TIME
    assert result.numerical_tie is False


def test_decision_is_independent_of_input_order_when_routes_are_distinguishable() -> None:
    worse = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=12_000,
            duration_seconds=1_800,
            toll_cost=Decimal("5.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )
    better = DecisionCandidate(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=1_200,
            toll_cost=Decimal("2.00"),
        ),
        energy_estimate=EnergyEstimate(cost=Decimal("4.00")),
    )

    forward_result = decide_route(
        [worse, better],
        value_of_time_per_hour=Decimal("20.00"),
        candidate_count=2,
        missing_data_present=False,
    )

    reversed_result = decide_route(
        [better, worse],
        value_of_time_per_hour=Decimal("20.00"),
        candidate_count=2,
        missing_data_present=False,
    )

    assert forward_result.recommended_route is better.route
    assert reversed_result.recommended_route is better.route
    assert forward_result.reason is DecisionReason.FASTER_AND_CHEAPER
    assert reversed_result.reason is DecisionReason.FASTER_AND_CHEAPER


def test_decide_route_rejects_negative_value_of_time() -> None:
    with pytest.raises(
        ValueError,
        match="value_of_time_per_hour cannot be negative",
    ):
        decide_route(
            [],
            value_of_time_per_hour=Decimal("-0.01"),
            candidate_count=0,
            missing_data_present=False,
        )


def test_calculate_cost_breakdown_exposes_authoritative_components() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_800,
        toll_cost=Decimal("2.00"),
    )
    candidate = DecisionCandidate(
        route=route,
        energy_estimate=EnergyEstimate(
            cost=Decimal("3.00"),
        ),
    )

    breakdown = calculate_cost_breakdown(
        candidate,
        Decimal("20.00"),
    )

    assert breakdown.monetary_cost == Decimal("5.00")
    assert breakdown.time_cost == Decimal("10.00")
    assert breakdown.generalized_cost == Decimal("15.00")
