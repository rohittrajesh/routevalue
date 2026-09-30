from decimal import Decimal

import pytest
from pydantic import ValidationError

from routevalue.api.schemas import (
    DecisionResponse,
    EligibilityResponse,
    EnergyEstimateResponse,
    RouteEvaluationResponse,
    RouteResponse,
    TripEvaluationRequest,
    TripEvaluationResponse,
)


def test_trip_evaluation_request_preserves_valid_values() -> None:
    request = TripEvaluationRequest(
        origin="  Origin  ",
        destination="  Destination  ",
        value_of_time_per_hour=Decimal("18.50"),
    )

    assert request.origin == "  Origin  "
    assert request.destination == "  Destination  "
    assert request.value_of_time_per_hour == Decimal("18.50")


@pytest.mark.parametrize(
    ("origin", "destination"),
    [
        ("", "Destination"),
        ("   ", "Destination"),
        ("Origin", ""),
        ("Origin", "   "),
    ],
)
def test_trip_evaluation_request_rejects_blank_endpoint(
    origin: str,
    destination: str,
) -> None:
    with pytest.raises(ValidationError):
        TripEvaluationRequest(
            origin=origin,
            destination=destination,
            value_of_time_per_hour=Decimal("18.00"),
        )


def test_trip_evaluation_request_allows_zero_value_of_time() -> None:
    request = TripEvaluationRequest(
        origin="Origin",
        destination="Destination",
        value_of_time_per_hour=Decimal(0),
    )

    assert request.value_of_time_per_hour == Decimal(0)


def test_trip_evaluation_request_rejects_negative_value_of_time() -> None:
    with pytest.raises(ValidationError):
        TripEvaluationRequest(
            origin="Origin",
            destination="Destination",
            value_of_time_per_hour=Decimal("-0.01"),
        )


def test_trip_evaluation_response_is_json_serializable() -> None:
    response = TripEvaluationResponse(
        route_evaluations=[
            RouteEvaluationResponse(
                route=RouteResponse(
                    distance_meters=10_000,
                    duration_seconds=900,
                    toll_cost=Decimal("1.50"),
                ),
                energy_estimate=EnergyEstimateResponse(
                    cost=Decimal("2.25"),
                ),
                eligibility=EligibilityResponse(
                    eligible=True,
                    reason=None,
                ),
            )
        ],
        decision=DecisionResponse(
            recommended_route=RouteResponse(
                distance_meters=10_000,
                duration_seconds=900,
                toll_cost=Decimal("1.50"),
            ),
            reason="only_eligible_route",
            numerical_tie=False,
            missing_data_present=False,
            candidate_count=1,
            eligible_count=1,
        ),
    )

    serialized = response.model_dump(mode="json")

    assert serialized["route_evaluations"][0]["route"]["toll_cost"] == "1.50"
    assert serialized["route_evaluations"][0]["energy_estimate"]["cost"] == "2.25"
