"""Final M5 contract tests for typed V2 energy consumption."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from routevalue.api.v2_evaluation_schemas import (
    V2ElectricConsumptionResponse,
    V2GasolineConsumptionResponse,
)
from routevalue.main import create_app


@pytest.mark.parametrize(
    ("model", "quantity"),
    [
        (V2GasolineConsumptionResponse, {"gallons": "4.25"}),
        (
            V2ElectricConsumptionResponse,
            {"kilowatt_hours": "35.625"},
        ),
    ],
)
def test_consumption_requires_explicit_energy_type(
    model: type[V2GasolineConsumptionResponse] | type[V2ElectricConsumptionResponse],
    quantity: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(quantity)


def test_openapi_requires_both_energy_discriminators() -> None:
    schemas = create_app().openapi()["components"]["schemas"]

    assert {
        "energy_type",
        "gallons",
    }.issubset(schemas["V2GasolineConsumptionResponse"]["required"])

    assert {
        "energy_type",
        "kilowatt_hours",
    }.issubset(schemas["V2ElectricConsumptionResponse"]["required"])


def test_openapi_uses_energy_type_discriminator() -> None:
    schemas = create_app().openapi()["components"]["schemas"]

    estimate = schemas["V2EnergyEstimateResponse"]
    consumption = estimate["properties"]["consumption"]

    branches = consumption.get("anyOf", [consumption])

    tagged = [branch for branch in branches if "discriminator" in branch]

    assert len(tagged) == 1

    discriminator = tagged[0]["discriminator"]

    assert discriminator["propertyName"] == "energy_type"
    assert set(discriminator["mapping"]) == {
        "gasoline",
        "electricity",
    }


def test_v1_energy_response_has_no_consumption_field() -> None:
    schemas = create_app().openapi()["components"]["schemas"]

    v1_energy = schemas["EnergyEstimateResponse"]

    assert set(v1_energy["properties"]) == {"cost"}


def test_typed_consumption_preserves_decimal_json_values() -> None:
    gasoline = V2GasolineConsumptionResponse(
        energy_type="gasoline",
        gallons=Decimal("4.250"),
    )
    electric = V2ElectricConsumptionResponse(
        energy_type="electricity",
        kilowatt_hours=Decimal("35.625"),
    )

    assert gasoline.model_dump(mode="json") == {
        "energy_type": "gasoline",
        "gallons": "4.250",
    }

    assert electric.model_dump(mode="json") == {
        "energy_type": "electricity",
        "kilowatt_hours": "35.625",
    }
