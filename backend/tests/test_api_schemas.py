from decimal import Decimal

import pytest
from pydantic import ValidationError

from routevalue.api.schemas import (
    CostBreakdownResponse,
    DecisionResponse,
    EligibilityResponse,
    EnergyEstimateResponse,
    GasolineGradeInput,
    GasolineInputs,
    RouteEvaluationResponse,
    RouteResponse,
    TripEvaluationRequest,
    TripEvaluationResponse,
)


def _gasoline_inputs() -> GasolineInputs:
    return GasolineInputs(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGradeInput.REGULAR,
        fuel_price_per_gallon=Decimal("4.50"),
    )


def test_trip_evaluation_request_preserves_valid_values() -> None:
    request = TripEvaluationRequest(
        origin="  Origin  ",
        destination="  Destination  ",
        value_of_time_per_hour=Decimal("18.50"),
        gasoline=_gasoline_inputs(),
    )

    assert request.origin == "  Origin  "
    assert request.destination == "  Destination  "
    assert request.value_of_time_per_hour == Decimal("18.50")
    assert request.gasoline.fuel_efficiency_mpg == Decimal(30)
    assert request.gasoline.fuel_grade is GasolineGradeInput.REGULAR
    assert request.gasoline.fuel_price_per_gallon == Decimal("4.50")


@pytest.mark.parametrize(
    "fuel_efficiency_mpg",
    [
        Decimal(0),
        Decimal(-1),
    ],
)
def test_gasoline_inputs_rejects_non_positive_fuel_efficiency(
    fuel_efficiency_mpg: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        GasolineInputs(
            fuel_efficiency_mpg=fuel_efficiency_mpg,
            fuel_grade=GasolineGradeInput.REGULAR,
            fuel_price_per_gallon=Decimal("4.50"),
        )


def test_gasoline_inputs_allows_zero_fuel_price() -> None:
    gasoline = GasolineInputs(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGradeInput.REGULAR,
        fuel_price_per_gallon=Decimal(0),
    )

    assert gasoline.fuel_price_per_gallon == Decimal(0)


def test_gasoline_inputs_rejects_negative_fuel_price() -> None:
    with pytest.raises(ValidationError):
        GasolineInputs(
            fuel_efficiency_mpg=Decimal(30),
            fuel_grade=GasolineGradeInput.REGULAR,
            fuel_price_per_gallon=Decimal("-0.01"),
        )


def test_gasoline_inputs_rejects_unknown_fuel_grade() -> None:
    with pytest.raises(ValidationError):
        GasolineInputs.model_validate(
            {
                "fuel_efficiency_mpg": "30",
                "fuel_grade": "diesel",
                "fuel_price_per_gallon": "4.50",
            }
        )


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
            gasoline=_gasoline_inputs(),
        )


def test_trip_evaluation_request_allows_zero_value_of_time() -> None:
    request = TripEvaluationRequest(
        origin="Origin",
        destination="Destination",
        value_of_time_per_hour=Decimal(0),
        gasoline=_gasoline_inputs(),
    )

    assert request.value_of_time_per_hour == Decimal(0)


def test_trip_evaluation_request_rejects_negative_value_of_time() -> None:
    with pytest.raises(ValidationError):
        TripEvaluationRequest(
            origin="Origin",
            destination="Destination",
            value_of_time_per_hour=Decimal("-0.01"),
            gasoline=_gasoline_inputs(),
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
                cost_breakdown=CostBreakdownResponse(
                    monetary_cost=Decimal("3.75"),
                    time_cost=Decimal("4.50"),
                    generalized_cost=Decimal("8.25"),
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
