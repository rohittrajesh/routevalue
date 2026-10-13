"""OpenAPI regression tests for V1 and V2 trip evaluations."""

from typing import Any

from routevalue.main import create_app


def _schema() -> dict[str, Any]:
    return create_app().openapi()


def test_v1_and_v2_evaluation_paths_coexist() -> None:
    paths = _schema()["paths"]

    assert "/trip-evaluations" in paths
    assert "/api/v2/trip-evaluations" in paths

    assert "post" in paths["/trip-evaluations"]
    assert "post" in paths["/api/v2/trip-evaluations"]


def test_v2_endpoint_uses_its_own_request_schema() -> None:
    schema = _schema()

    operation = schema["paths"]["/api/v2/trip-evaluations"]["post"]
    body = operation["requestBody"]["content"]["application/json"]

    assert body["schema"]["$ref"] == ("#/components/schemas/V2TripEvaluationRequest")

    request_schema = schema["components"]["schemas"]["V2TripEvaluationRequest"]

    assert set(request_schema["required"]) == {
        "origin",
        "destination",
    }

    assert request_schema["additionalProperties"] is False

    fields = request_schema["properties"]

    assert "saved_vehicle_id" in fields
    assert "gasoline" in fields
    assert "electricity" in fields

    assert "value_of_time_per_hour" not in fields
    assert "user_id" not in fields
    assert "fuel_efficiency_mpg" not in fields
    assert "fuel_grade" not in fields


def test_v2_gasoline_contract_allows_only_price() -> None:
    schema = _schema()["components"]["schemas"]["V2GasolineInputs"]

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"fuel_price_per_gallon"}
    assert set(schema["properties"]) == {"fuel_price_per_gallon"}


def test_v2_electricity_contract_allows_only_price() -> None:
    schema = _schema()["components"]["schemas"]["V2ElectricityInputs"]

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"price_per_kilowatt_hour"}
    assert set(schema["properties"]) == {"price_per_kilowatt_hour"}

    assert "combined_kwh_per_mile" not in schema["properties"]


def test_v1_response_is_preserved_and_v2_has_own_response() -> None:
    schema = _schema()

    v1 = schema["paths"]["/trip-evaluations"]["post"]
    v2 = schema["paths"]["/api/v2/trip-evaluations"]["post"]

    def response_reference(operation: dict[str, Any]) -> str:
        reference = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]

        assert isinstance(reference, str)

        return reference

    assert response_reference(v1) == ("#/components/schemas/TripEvaluationResponse")
    assert response_reference(v2) == ("#/components/schemas/V2TripEvaluationResponse")


def test_v2_energy_response_documents_typed_consumption() -> None:
    schemas = _schema()["components"]["schemas"]

    assert "V2EnergyEstimateResponse" in schemas
    assert "V2GasolineConsumptionResponse" in schemas
    assert "V2ElectricConsumptionResponse" in schemas

    gasoline = schemas["V2GasolineConsumptionResponse"]
    electric = schemas["V2ElectricConsumptionResponse"]

    assert "gallons" in gasoline["properties"]
    assert "kilowatt_hours" in electric["properties"]

    assert "consumption" in schemas["V2EnergyEstimateResponse"]["properties"]


def test_v2_endpoint_documents_authentication_and_failures() -> None:
    operation = _schema()["paths"]["/api/v2/trip-evaluations"]["post"]

    assert operation.get("security")

    assert {
        "200",
        "401",
        "404",
        "409",
        "422",
        "500",
        "502",
        "503",
    }.issubset(operation["responses"])


def test_v1_request_fields_remain_unchanged() -> None:
    schemas = _schema()["components"]["schemas"]

    v1_request = schemas["TripEvaluationRequest"]

    assert set(v1_request["required"]) == {
        "origin",
        "destination",
        "value_of_time_per_hour",
        "gasoline",
    }

    assert "saved_vehicle_id" not in v1_request["properties"]
    assert "electricity" not in v1_request["properties"]

    v1_gasoline = schemas["GasolineInputs"]

    assert set(v1_gasoline["required"]) == {
        "fuel_efficiency_mpg",
        "fuel_grade",
        "fuel_price_per_gallon",
    }


def test_v2_profile_error_codes_are_documented() -> None:
    codes = set(_schema()["components"]["schemas"]["ApiErrorCode"]["enum"])

    assert {
        "value_of_time_not_configured",
        "default_vehicle_not_configured",
        "default_vehicle_unavailable",
        "saved_vehicle_not_found",
        "unsupported_vehicle_energy_type",
        "energy_input_mismatch",
        "profile_service_unavailable",
        "profile_state_invalid",
    }.issubset(codes)
