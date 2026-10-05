from decimal import Decimal

import pytest

from routevalue.application.models import (
    ResolvedLocation,
    RouteEvaluation,
    TripEvaluationResult,
)
from routevalue.domain.models import (
    CostBreakdown,
    DecisionReason,
    DecisionResult,
    EligibilityResult,
    EnergyEstimate,
    IneligibilityReason,
    RouteCandidate,
)


def test_resolved_location_preserves_normalized_location_data() -> None:
    location = ResolvedLocation(
        display_name="UC San Diego",
        latitude=32.8801,
        longitude=-117.2340,
        source="google_places",
        source_id="test-place-id",
    )

    assert location.display_name == "UC San Diego"
    assert location.latitude == 32.8801
    assert location.longitude == -117.2340
    assert location.source == "google_places"
    assert location.source_id == "test-place-id"


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (-90.01, 0),
        (90.01, 0),
        (0, -180.01),
        (0, 180.01),
    ],
)
def test_resolved_location_rejects_invalid_coordinates(
    latitude: float,
    longitude: float,
) -> None:
    with pytest.raises(ValueError):
        ResolvedLocation(
            display_name="Location",
            latitude=latitude,
            longitude=longitude,
        )


@pytest.mark.parametrize(
    ("source", "source_id"),
    [
        ("google_places", None),
        (None, "place-id"),
        ("", "place-id"),
        ("google_places", ""),
    ],
)
def test_resolved_location_rejects_invalid_external_reference(
    source: str | None,
    source_id: str | None,
) -> None:
    with pytest.raises(ValueError):
        ResolvedLocation(
            display_name="Location",
            latitude=32.88,
            longitude=-117.23,
            source=source,
            source_id=source_id,
        )


def test_trip_evaluation_result_preserves_route_evaluations_and_decision() -> None:
    eligible_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    ineligible_route = RouteCandidate(
        distance_meters=12_000,
        duration_seconds=1_000,
        toll_cost=None,
    )

    eligible_evaluation = RouteEvaluation(
        route=eligible_route,
        energy_estimate=EnergyEstimate(cost=Decimal("1.25")),
        eligibility=EligibilityResult(
            eligible=True,
            reason=None,
        ),
        cost_breakdown=CostBreakdown(
            monetary_cost=Decimal("1.25"),
            time_cost=Decimal("4.50"),
            generalized_cost=Decimal("5.75"),
        ),
    )

    ineligible_evaluation = RouteEvaluation(
        route=ineligible_route,
        energy_estimate=EnergyEstimate(cost=Decimal("1.50")),
        eligibility=EligibilityResult(
            eligible=False,
            reason=IneligibilityReason.MISSING_TOLL_COST,
        ),
        cost_breakdown=None,
    )

    decision = DecisionResult(
        recommended_route=eligible_route,
        reason=DecisionReason.ONLY_ELIGIBLE_ROUTE,
        numerical_tie=False,
        missing_data_present=True,
        candidate_count=2,
        eligible_count=1,
    )

    result = TripEvaluationResult(
        route_evaluations=(
            eligible_evaluation,
            ineligible_evaluation,
        ),
        decision=decision,
    )

    assert result.route_evaluations == (
        eligible_evaluation,
        ineligible_evaluation,
    )
    assert result.decision == decision


def test_trip_evaluation_result_rejects_candidate_count_mismatch() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    evaluation = RouteEvaluation(
        route=route,
        energy_estimate=EnergyEstimate(cost=Decimal("1.25")),
        eligibility=EligibilityResult(
            eligible=True,
            reason=None,
        ),
        cost_breakdown=CostBreakdown(
            monetary_cost=Decimal("1.25"),
            time_cost=Decimal("4.50"),
            generalized_cost=Decimal("5.75"),
        ),
    )
    decision = DecisionResult(
        recommended_route=route,
        reason=DecisionReason.ONLY_ELIGIBLE_ROUTE,
        numerical_tie=False,
        missing_data_present=False,
        candidate_count=2,
        eligible_count=1,
    )

    with pytest.raises(
        ValueError,
        match="route evaluation count must match decision candidate count",
    ):
        TripEvaluationResult(
            route_evaluations=(evaluation,),
            decision=decision,
        )


def test_trip_evaluation_result_rejects_eligible_count_mismatch() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    evaluation = RouteEvaluation(
        route=route,
        energy_estimate=EnergyEstimate(cost=Decimal("1.25")),
        eligibility=EligibilityResult(
            eligible=True,
            reason=None,
        ),
        cost_breakdown=CostBreakdown(
            monetary_cost=Decimal("1.25"),
            time_cost=Decimal("4.50"),
            generalized_cost=Decimal("5.75"),
        ),
    )
    decision = DecisionResult(
        recommended_route=None,
        reason=None,
        numerical_tie=False,
        missing_data_present=False,
        candidate_count=1,
        eligible_count=0,
    )

    with pytest.raises(
        ValueError,
        match="eligible route evaluation count must match decision eligible count",
    ):
        TripEvaluationResult(
            route_evaluations=(evaluation,),
            decision=decision,
        )


def test_trip_evaluation_result_rejects_missing_data_mismatch() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=None,
    )
    evaluation = RouteEvaluation(
        route=route,
        energy_estimate=EnergyEstimate(cost=Decimal("1.25")),
        eligibility=EligibilityResult(
            eligible=False,
            reason=IneligibilityReason.MISSING_TOLL_COST,
        ),
        cost_breakdown=None,
    )
    decision = DecisionResult(
        recommended_route=None,
        reason=None,
        numerical_tie=False,
        missing_data_present=False,
        candidate_count=1,
        eligible_count=0,
    )

    with pytest.raises(
        ValueError,
        match="route evaluation missing-data state must match decision",
    ):
        TripEvaluationResult(
            route_evaluations=(evaluation,),
            decision=decision,
        )
