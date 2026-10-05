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
    ResolvedLocationInput,
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


def _resolved_location_input(
    display_name: str = "Location",
    *,
    source_id: str = "test-place-id",
) -> ResolvedLocationInput:
    return ResolvedLocationInput(
        display_name=display_name,
        latitude=32.88,
        longitude=-117.23,
        source="google_places",
        source_id=source_id,
    )


def test_trip_evaluation_request_preserves_valid_values() -> None:
    request = TripEvaluationRequest(
        origin=_resolved_location_input(
            "Origin",
            source_id="origin-place-id",
        ),
        destination=_resolved_location_input(
            "Destination",
            source_id="destination-place-id",
        ),
        value_of_time_per_hour=Decimal("18.50"),
        gasoline=_gasoline_inputs(),
    )

    assert request.origin.display_name == "Origin"
    assert request.origin.latitude == 32.88
    assert request.origin.longitude == -117.23
    assert request.origin.source == "google_places"
    assert request.origin.source_id == "origin-place-id"

    assert request.destination.display_name == "Destination"
    assert request.destination.latitude == 32.88
    assert request.destination.longitude == -117.23
    assert request.destination.source == "google_places"
    assert request.destination.source_id == "destination-place-id"

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
    ("field", "value"),
    [
        ("origin", "Origin"),
        ("destination", "Destination"),
    ],
)
def test_trip_evaluation_request_rejects_unresolved_string_endpoint(
    field: str,
    value: str,
) -> None:
    payload: dict[str, object] = {
        "origin": _resolved_location_input(
            "Origin",
            source_id="origin-place-id",
        ).model_dump(),
        "destination": _resolved_location_input(
            "Destination",
            source_id="destination-place-id",
        ).model_dump(),
        "value_of_time_per_hour": "18.00",
        "gasoline": _gasoline_inputs().model_dump(),
    }

    payload[field] = value

    with pytest.raises(ValidationError):
        TripEvaluationRequest.model_validate(payload)


def test_trip_evaluation_request_allows_zero_value_of_time() -> None:
    request = TripEvaluationRequest(
        origin=_resolved_location_input(
            "Origin",
            source_id="origin-place-id",
        ),
        destination=_resolved_location_input(
            "Destination",
            source_id="destination-place-id",
        ),
        value_of_time_per_hour=Decimal(0),
        gasoline=_gasoline_inputs(),
    )

    assert request.value_of_time_per_hour == Decimal(0)


def test_trip_evaluation_request_rejects_negative_value_of_time() -> None:
    with pytest.raises(ValidationError):
        TripEvaluationRequest(
            origin=_resolved_location_input(
                "Origin",
                source_id="origin-place-id",
            ),
            destination=_resolved_location_input(
                "Destination",
                source_id="destination-place-id",
            ),
            value_of_time_per_hour=Decimal("-0.01"),
            gasoline=_gasoline_inputs(),
        )


def test_resolved_location_input_preserves_normalized_values() -> None:
    location = ResolvedLocationInput(
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


def test_resolved_location_input_rejects_blank_display_name() -> None:
    with pytest.raises(ValidationError):
        ResolvedLocationInput(
            display_name="   ",
            latitude=32.88,
            longitude=-117.23,
        )


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (-90.01, 0),
        (90.01, 0),
        (0, -180.01),
        (0, 180.01),
    ],
)
def test_resolved_location_input_rejects_invalid_coordinates(
    latitude: float,
    longitude: float,
) -> None:
    with pytest.raises(ValidationError):
        ResolvedLocationInput(
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
def test_resolved_location_input_rejects_invalid_external_reference(
    source: str | None,
    source_id: str | None,
) -> None:
    with pytest.raises(ValidationError):
        ResolvedLocationInput(
            display_name="Location",
            latitude=32.88,
            longitude=-117.23,
            source=source,
            source_id=source_id,
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
