"""Contract tests for authenticated V2 profile-driven trip evaluation."""

from copy import deepcopy
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from routevalue.api import schemas
from routevalue.main import create_app

_V2_PATH = "/api/v2/trip-evaluations"
_V1_PATH = "/trip-evaluations"


def _valid_v2_body() -> dict[str, object]:
    """Build the smallest valid gasoline profile-driven request."""

    return {
        "origin": {
            "display_name": "UC San Diego",
            "latitude": 32.8801,
            "longitude": -117.2340,
        },
        "destination": {
            "display_name": "Downtown San Diego",
            "latitude": 32.7157,
            "longitude": -117.1611,
        },
        "gasoline": {
            "fuel_price_per_gallon": "4.590125",
        },
    }


def _v2_request_model() -> type[BaseModel]:
    """Find the new contract without causing an import-time failure."""

    model = getattr(
        schemas,
        "V2TripEvaluationRequest",
        None,
    )

    assert isinstance(model, type), "V2TripEvaluationRequest has not been implemented"
    assert issubclass(model, BaseModel)

    return model


def test_v1_trip_evaluation_contract_remains_unchanged() -> None:
    """V1 must continue requiring its original personalization inputs."""

    body = _valid_v2_body()

    with pytest.raises(ValidationError):
        schemas.TripEvaluationRequest.model_validate(body)

    complete_body = deepcopy(body)

    complete_body["value_of_time_per_hour"] = "25.75"
    complete_body["gasoline"] = {
        "fuel_efficiency_mpg": "32.125",
        "fuel_grade": "regular",
        "fuel_price_per_gallon": "4.590125",
    }

    request = schemas.TripEvaluationRequest.model_validate(complete_body)

    assert request.value_of_time_per_hour == Decimal("25.75")
    assert request.gasoline.fuel_efficiency_mpg == Decimal("32.125")
    assert request.gasoline.fuel_grade.value == "regular"

    openapi = create_app().openapi()

    assert "post" in openapi["paths"][_V1_PATH]


def test_v2_request_supports_default_vehicle_selection() -> None:
    """An omitted vehicle ID must select the persisted default."""

    request = _v2_request_model().model_validate(_valid_v2_body())

    assert request.model_dump()["saved_vehicle_id"] is None


def test_v2_request_supports_explicit_vehicle_selection() -> None:
    """An explicit vehicle ID must be retained as a UUID."""

    vehicle_id = uuid4()
    body = _valid_v2_body()

    body["saved_vehicle_id"] = str(vehicle_id)

    request = _v2_request_model().model_validate(body)
    selected_id = request.model_dump()["saved_vehicle_id"]

    assert selected_id == vehicle_id
    assert isinstance(selected_id, UUID)


def test_v2_request_accepts_explicit_null_vehicle_selection() -> None:
    """Explicit null must have the same meaning as an omitted ID."""

    body = _valid_v2_body()
    body["saved_vehicle_id"] = None

    request = _v2_request_model().model_validate(body)

    assert request.model_dump()["saved_vehicle_id"] is None


def test_v2_request_preserves_exact_decimal_price() -> None:
    """Gasoline pricing must not lose precision through float conversion."""

    request = _v2_request_model().model_validate(_valid_v2_body())

    gasoline = request.model_dump()["gasoline"]

    assert isinstance(gasoline, dict)

    price = gasoline["fuel_price_per_gallon"]

    assert isinstance(price, Decimal)
    assert price == Decimal("4.590125")


def test_v2_request_accepts_zero_gasoline_price() -> None:
    """Zero is a known price, not missing data."""

    body = _valid_v2_body()
    gasoline = body["gasoline"]

    assert isinstance(gasoline, dict)

    gasoline["fuel_price_per_gallon"] = "0"

    request = _v2_request_model().model_validate(body)
    resolved_gasoline = request.model_dump()["gasoline"]

    assert isinstance(resolved_gasoline, dict)
    assert resolved_gasoline["fuel_price_per_gallon"] == Decimal(0)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("user_id", str(uuid4())),
        ("value_of_time_per_hour", "999"),
        ("fuel_efficiency_mpg", "999"),
        ("fuel_grade", "premium"),
    ],
)
def test_v2_request_forbids_client_profile_overrides(
    field_name: str,
    field_value: str,
) -> None:
    """Identity and persisted personalization cannot come from the client."""

    body = _valid_v2_body()
    body[field_name] = field_value

    with pytest.raises(ValidationError):
        _v2_request_model().model_validate(body)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("fuel_efficiency_mpg", "999"),
        ("fuel_grade", "premium"),
        ("source", "regional_market"),
    ],
)
def test_v2_gasoline_input_forbids_specification_overrides(
    field_name: str,
    field_value: str,
) -> None:
    """Gasoline request data must contain only the current price."""

    body = _valid_v2_body()
    gasoline = body["gasoline"]

    assert isinstance(gasoline, dict)

    gasoline[field_name] = field_value

    with pytest.raises(ValidationError):
        _v2_request_model().model_validate(body)


@pytest.mark.parametrize(
    "invalid_price",
    [
        "-0.01",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_v2_request_rejects_invalid_gasoline_prices(
    invalid_price: str,
) -> None:
    """Negative and non-finite gasoline prices are invalid."""

    body = _valid_v2_body()
    gasoline = body["gasoline"]

    assert isinstance(gasoline, dict)

    gasoline["fuel_price_per_gallon"] = invalid_price

    with pytest.raises(ValidationError):
        _v2_request_model().model_validate(body)


def test_v2_request_requires_gasoline_price() -> None:
    """M4 has no automatic price provider or implicit price default."""

    body = _valid_v2_body()
    body["gasoline"] = {}

    with pytest.raises(ValidationError):
        _v2_request_model().model_validate(body)


def test_v2_request_rejects_invalid_vehicle_uuid() -> None:
    """Saved vehicle selection must use a valid UUID."""

    body = _valid_v2_body()
    body["saved_vehicle_id"] = "not-a-uuid"

    with pytest.raises(ValidationError):
        _v2_request_model().model_validate(body)


def test_v2_endpoint_uses_existing_evaluation_response() -> None:
    """V2 must preserve the authoritative V1 decision representation."""

    openapi = create_app().openapi()

    operation = openapi["paths"][_V2_PATH]["post"]

    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert response_schema["$ref"] == ("#/components/schemas/TripEvaluationResponse")


def test_v2_endpoint_requires_authentication() -> None:
    """An unauthenticated request must not reach trip evaluation."""

    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            _V2_PATH,
            json=_valid_v2_body(),
        )

    assert response.status_code == 401

    assert response.json() == {
        "code": "authentication_required",
        "detail": "Authentication is required.",
    }

    assert response.headers["www-authenticate"] == "Bearer"
