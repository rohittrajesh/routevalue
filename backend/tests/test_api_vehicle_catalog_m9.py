"""Contract and authorization tests for M9 vehicle catalog browsing."""

from uuid import uuid4

from fastapi.testclient import TestClient

from routevalue.api.saved_vehicles import (
    get_vehicle_specification_provider,
)
from routevalue.api.user_identity import get_authenticated_user
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.models import VehicleCatalogConfiguration
from routevalue.domain.identity import UserId
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovTransportError,
)
from routevalue.main import create_app


class FakeCatalogProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.unavailable = False

    def list_years(self) -> tuple[int, ...]:
        self.calls.append(("years",))

        if self.unavailable:
            raise FuelEconomyGovTransportError("Provider unavailable")

        return (2026, 2025)

    def list_makes(self, *, year: int) -> tuple[str, ...]:
        self.calls.append(("makes", year))
        return ("Honda", "Toyota")

    def list_models(
        self,
        *,
        year: int,
        make: str,
    ) -> tuple[str, ...]:
        self.calls.append(("models", year, make))
        return ("Camry",)

    def list_configurations(
        self,
        *,
        year: int,
        make: str,
        model: str,
    ) -> tuple[VehicleCatalogConfiguration, ...]:
        self.calls.append(("configurations", year, make, model))

        return (
            VehicleCatalogConfiguration(
                year=year,
                make=make,
                model=model,
                configuration="2.5L 4cyl CVT (FWD)",
                source="fueleconomy_gov",
                source_id="12345",
            ),
        )


def _client(
    provider: FakeCatalogProvider,
) -> TestClient:
    app = create_app()

    user_id = UserId(value=uuid4())

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)

    app.dependency_overrides[get_vehicle_specification_provider] = lambda: provider

    return TestClient(app)


def test_catalog_years() -> None:
    provider = FakeCatalogProvider()

    response = _client(provider).get("/api/v2/vehicle-catalog/years")

    assert response.status_code == 200
    assert response.json() == {"years": [2026, 2025]}
    assert provider.calls == [("years",)]


def test_catalog_makes() -> None:
    provider = FakeCatalogProvider()

    response = _client(provider).get(
        "/api/v2/vehicle-catalog/makes",
        params={"year": "2026"},
    )

    assert response.status_code == 200
    assert response.json() == {"makes": ["Honda", "Toyota"]}
    assert provider.calls == [("makes", 2026)]


def test_catalog_models() -> None:
    provider = FakeCatalogProvider()

    response = _client(provider).get(
        "/api/v2/vehicle-catalog/models",
        params={"year": 2026, "make": "Toyota"},
    )

    assert response.status_code == 200
    assert response.json() == {"models": ["Camry"]}
    assert provider.calls == [("models", 2026, "Toyota")]


def test_catalog_configurations_preserve_provenance() -> None:
    provider = FakeCatalogProvider()

    response = _client(provider).get(
        "/api/v2/vehicle-catalog/configurations",
        params={
            "year": 2026,
            "make": "Toyota",
            "model": "Camry",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "configurations": [
            {
                "year": 2026,
                "make": "Toyota",
                "model": "Camry",
                "configuration": "2.5L 4cyl CVT (FWD)",
                "source": "fueleconomy_gov",
                "source_id": "12345",
            }
        ],
    }


def test_catalog_rejects_invalid_year_before_provider_call() -> None:
    provider = FakeCatalogProvider()

    response = _client(provider).get(
        "/api/v2/vehicle-catalog/makes",
        params={"year": 0},
    )

    assert response.status_code == 422
    assert provider.calls == []


def test_catalog_rejects_blank_make() -> None:
    provider = FakeCatalogProvider()

    response = _client(provider).get(
        "/api/v2/vehicle-catalog/models",
        params={"year": 2026, "make": "   "},
    )

    assert response.status_code == 422
    assert provider.calls == []


def test_catalog_rejects_missing_required_query() -> None:
    provider = FakeCatalogProvider()

    response = _client(provider).get(
        "/api/v2/vehicle-catalog/configurations",
        params={"year": 2026, "make": "Toyota"},
    )

    assert response.status_code == 422
    assert provider.calls == []


def test_catalog_requires_authentication() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v2/vehicle-catalog/years")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_catalog_provider_outage_maps_to_public_error() -> None:
    provider = FakeCatalogProvider()
    provider.unavailable = True

    response = _client(provider).get("/api/v2/vehicle-catalog/years")

    assert response.status_code == 503
    assert response.json()["code"] == ("vehicle_catalog_service_unavailable")
