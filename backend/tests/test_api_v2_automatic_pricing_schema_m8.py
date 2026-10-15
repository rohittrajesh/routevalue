"""M8-R3 tests for optional automatic gasoline pricing request contracts."""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from routevalue.api.schemas import V2TripEvaluationRequest


def make_body() -> dict[str, object]:
    return {
        "origin": {
            "display_name": "UC San Diego",
            "latitude": 32.8801,
            "longitude": -117.234,
        },
        "destination": {
            "display_name": "Downtown San Diego",
            "latitude": 32.7157,
            "longitude": -117.1611,
        },
    }


def test_omitted_energy_inputs_enable_automatic_pricing_request() -> None:
    request = V2TripEvaluationRequest.model_validate(make_body())

    assert request.gasoline is None
    assert request.electricity is None


def test_explicit_null_energy_inputs_are_accepted() -> None:
    body = make_body()
    body["gasoline"] = None
    body["electricity"] = None

    request = V2TripEvaluationRequest.model_validate(body)

    assert request.gasoline is None
    assert request.electricity is None


def test_manual_gasoline_price_remains_supported() -> None:
    body = make_body()
    body["gasoline"] = {"fuel_price_per_gallon": "4.50"}

    request = V2TripEvaluationRequest.model_validate(body)

    assert request.gasoline is not None
    assert request.gasoline.fuel_price_per_gallon == Decimal("4.50")
    assert request.electricity is None


def test_manual_electricity_price_remains_supported() -> None:
    body = make_body()
    body["electricity"] = {"price_per_kilowatt_hour": "0.25"}

    request = V2TripEvaluationRequest.model_validate(body)

    assert request.electricity is not None
    assert request.electricity.price_per_kilowatt_hour == Decimal("0.25")
    assert request.gasoline is None


def test_explicit_saved_vehicle_is_preserved_without_price() -> None:
    vehicle_id = uuid4()
    body = make_body()
    body["saved_vehicle_id"] = str(vehicle_id)

    request = V2TripEvaluationRequest.model_validate(body)

    assert request.saved_vehicle_id == vehicle_id
    assert request.gasoline is None
    assert request.electricity is None


def test_conflicting_energy_inputs_are_rejected() -> None:
    body = make_body()
    body["gasoline"] = {"fuel_price_per_gallon": "4.50"}
    body["electricity"] = {"price_per_kilowatt_hour": "0.25"}

    with pytest.raises(ValidationError, match="cannot both be supplied"):
        V2TripEvaluationRequest.model_validate(body)


def test_empty_gasoline_object_is_rejected() -> None:
    body = make_body()
    body["gasoline"] = {}

    with pytest.raises(ValidationError):
        V2TripEvaluationRequest.model_validate(body)


@pytest.mark.parametrize(
    "invalid_price",
    [
        "-0.01",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_invalid_manual_gasoline_prices_are_rejected(
    invalid_price: str,
) -> None:
    body = make_body()
    body["gasoline"] = {"fuel_price_per_gallon": invalid_price}

    with pytest.raises(ValidationError):
        V2TripEvaluationRequest.model_validate(body)


def test_unexpected_user_id_is_rejected() -> None:
    body = make_body()
    body["user_id"] = str(uuid4())

    with pytest.raises(ValidationError):
        V2TripEvaluationRequest.model_validate(body)
