"""Security and provider-failure hardening for V2 saved vehicles."""

from collections.abc import Sequence
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from routevalue.api.saved_vehicles import (
    get_saved_vehicle_repository,
    get_vehicle_specification_provider,
)
from routevalue.api.user_identity import (
    get_authenticated_user,
)
from routevalue.application.identity import (
    AuthenticatedUser,
)
from routevalue.application.models import (
    VehicleCatalogConfiguration,
    VehicleSpecificationLookupResult,
)
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleSnapshot,
)
from routevalue.domain.identity import (
    SavedVehicleId,
    UserId,
)
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovError,
    FuelEconomyGovHTTPError,
    FuelEconomyGovResponseError,
    FuelEconomyGovTransportError,
)
from routevalue.main import create_app


class UnusedRepository:
    """Repository that must not be reached during provider failures."""

    def list_vehicles(
        self,
        user_id: UserId,
    ) -> Sequence[SavedVehicle]:
        del user_id
        raise AssertionError("repository should not be reached")

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        del user_id
        del vehicle_id
        raise AssertionError("repository should not be reached")

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        del user_id
        del snapshot
        raise AssertionError("repository should not be reached")

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        del user_id
        del vehicle_id
        raise AssertionError("repository should not be reached")


class FailingProvider:
    """Fail before a selected configuration can be revalidated."""

    def __init__(
        self,
        error: FuelEconomyGovError,
    ) -> None:
        self._error = error

    def list_years(self) -> Sequence[int]:
        raise self._error

    def list_makes(
        self,
        *,
        year: int,
    ) -> Sequence[str]:
        del year
        raise self._error

    def list_models(
        self,
        *,
        year: int,
        make: str,
    ) -> Sequence[str]:
        del year
        del make
        raise self._error

    def list_configurations(
        self,
        *,
        year: int,
        make: str,
        model: str,
    ) -> Sequence[VehicleCatalogConfiguration]:
        del year
        del make
        del model
        raise self._error

    def get_specification(
        self,
        configuration: VehicleCatalogConfiguration,
    ) -> VehicleSpecificationLookupResult:
        del configuration
        raise self._error


def _failing_client(
    error: FuelEconomyGovError,
) -> TestClient:
    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(
        user_id=UserId(value=uuid4())
    )

    app.dependency_overrides[get_saved_vehicle_repository] = lambda: UnusedRepository()

    app.dependency_overrides[get_vehicle_specification_provider] = lambda: FailingProvider(error)

    return TestClient(app)


def _valid_create_payload() -> dict[str, object]:
    return {
        "year": 2025,
        "make": "Toyota",
        "model": "Camry",
        "configuration": "2.5L 4cyl CVT (FWD)",
        "source": "fueleconomy_gov",
        "source_id": "12345",
    }


def test_saved_vehicle_endpoints_require_bearer_authentication_in_openapi() -> None:
    schema = create_app().openapi()

    bearer_schemes = {
        name
        for name, definition in schema["components"]["securitySchemes"].items()
        if definition.get("type") == "http" and definition.get("scheme") == "bearer"
    }

    assert bearer_schemes

    operations = (
        (
            "/api/v2/vehicles",
            "get",
        ),
        (
            "/api/v2/vehicles",
            "post",
        ),
        (
            "/api/v2/vehicles/{vehicle_id}",
            "get",
        ),
        (
            "/api/v2/vehicles/{vehicle_id}",
            "delete",
        ),
    )

    for path, method in operations:
        operation = schema["paths"][path][method]

        configured_schemes = {name for requirement in operation["security"] for name in requirement}

        assert configured_schemes & bearer_schemes


def test_saved_vehicle_create_contract_contains_no_user_or_efficiency_fields() -> None:
    schema = create_app().openapi()

    request_schema = schema["components"]["schemas"]["SavedVehicleCreateRequest"]

    assert set(request_schema["properties"]) == {
        "year",
        "make",
        "model",
        "configuration",
        "source",
        "source_id",
    }

    assert request_schema["additionalProperties"] is False


def test_saved_vehicle_collection_without_bearer_returns_401() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v2/vehicles")

    assert response.status_code == 401

    assert response.json() == {
        "code": "authentication_required",
        "detail": "Authentication is required.",
    }

    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    (
        "error",
        "expected_status",
        "expected_code",
    ),
    [
        (
            FuelEconomyGovTransportError("network unavailable"),
            503,
            "vehicle_catalog_service_unavailable",
        ),
        (
            FuelEconomyGovHTTPError(503),
            503,
            "vehicle_catalog_service_unavailable",
        ),
        (
            FuelEconomyGovHTTPError(400),
            502,
            "vehicle_catalog_service_error",
        ),
        (
            FuelEconomyGovResponseError("invalid provider response"),
            502,
            "vehicle_catalog_response_invalid",
        ),
    ],
)
def test_vehicle_provider_failures_are_safely_mapped(
    error: FuelEconomyGovError,
    expected_status: int,
    expected_code: str,
) -> None:
    with _failing_client(error) as client:
        response = client.post(
            "/api/v2/vehicles",
            json=_valid_create_payload(),
        )

    assert response.status_code == expected_status

    assert response.json()["code"] == expected_code
