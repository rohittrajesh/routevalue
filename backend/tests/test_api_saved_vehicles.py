"""Tests for the authenticated V2 saved-vehicle API."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

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
    VehicleSpecificationUnavailableReason,
)
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleSnapshot,
)
from routevalue.domain.identity import (
    SavedVehicleId,
    UserId,
)
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
)
from routevalue.main import create_app

_RETRIEVED_AT = datetime(
    2026,
    10,
    12,
    20,
    0,
    tzinfo=UTC,
)

_SAVED_AT = datetime(
    2026,
    10,
    12,
    20,
    1,
    tzinfo=UTC,
)


def _configuration() -> VehicleCatalogConfiguration:
    return VehicleCatalogConfiguration(
        year=2025,
        make="Toyota",
        model="Camry",
        configuration="2.5L 4cyl CVT (FWD)",
        source="fueleconomy_gov",
        source_id="12345",
    )


def _gasoline_specification() -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal("32.125"),
        city_mpg=Decimal("28.5"),
        highway_mpg=Decimal("38.25"),
        fuel_grade=GasolineGrade.REGULAR,
    )


class FakeSavedVehicleRepository:
    """In-memory owner-scoped saved-vehicle repository."""

    def __init__(self) -> None:
        self.vehicles: dict[
            tuple[
                UserId,
                SavedVehicleId,
            ],
            SavedVehicle,
        ] = {}

    def list_vehicles(
        self,
        user_id: UserId,
    ) -> Sequence[SavedVehicle]:
        return tuple(
            vehicle
            for (
                owner_id,
                _,
            ), vehicle in self.vehicles.items()
            if owner_id == user_id
        )

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        return self.vehicles.get(
            (
                user_id,
                vehicle_id,
            )
        )

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        vehicle = SavedVehicle(
            id=SavedVehicleId(value=uuid4()),
            configuration=(snapshot.configuration),
            specification=(snapshot.specification),
            specification_retrieved_at=(snapshot.specification_retrieved_at),
            saved_at=_SAVED_AT,
        )

        self.vehicles[
            (
                user_id,
                vehicle.id,
            )
        ] = vehicle

        return vehicle

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        return (
            self.vehicles.pop(
                (
                    user_id,
                    vehicle_id,
                ),
                None,
            )
            is not None
        )


class FakeVehicleSpecificationProvider:
    """Return one canonical test catalog configuration."""

    def __init__(
        self,
        result: VehicleSpecificationLookupResult,
    ) -> None:
        self.result = result

    def list_years(self) -> Sequence[int]:
        return ()

    def list_makes(
        self,
        *,
        year: int,
    ) -> Sequence[str]:
        del year
        return ()

    def list_models(
        self,
        *,
        year: int,
        make: str,
    ) -> Sequence[str]:
        del year
        del make
        return ()

    def list_configurations(
        self,
        *,
        year: int,
        make: str,
        model: str,
    ) -> Sequence[VehicleCatalogConfiguration]:
        configuration = _configuration()

        if (
            year == configuration.year
            and make == configuration.make
            and model == configuration.model
        ):
            return (configuration,)

        return ()

    def get_specification(
        self,
        configuration: VehicleCatalogConfiguration,
    ) -> VehicleSpecificationLookupResult:
        assert configuration == _configuration()
        return self.result


def _client(
    *,
    user_id: UserId,
    repository: FakeSavedVehicleRepository,
    provider: FakeVehicleSpecificationProvider,
) -> TestClient:
    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)

    app.dependency_overrides[get_saved_vehicle_repository] = lambda: repository

    app.dependency_overrides[get_vehicle_specification_provider] = lambda: provider

    return TestClient(app)


def test_list_saved_vehicles_starts_empty() -> None:
    user_id = UserId(value=uuid4())

    client = _client(
        user_id=user_id,
        repository=FakeSavedVehicleRepository(),
        provider=FakeVehicleSpecificationProvider(
            VehicleSpecificationLookupResult(
                specification=(_gasoline_specification()),
                unavailable_reason=None,
            )
        ),
    )

    response = client.get("/api/v2/vehicles")

    assert response.status_code == 200
    assert response.json() == {
        "vehicles": [],
    }


def test_create_saved_vehicle_returns_server_specification() -> None:
    user_id = UserId(value=uuid4())

    repository = FakeSavedVehicleRepository()

    client = _client(
        user_id=user_id,
        repository=repository,
        provider=FakeVehicleSpecificationProvider(
            VehicleSpecificationLookupResult(
                specification=(_gasoline_specification()),
                unavailable_reason=None,
            )
        ),
    )

    configuration = _configuration()

    response = client.post(
        "/api/v2/vehicles",
        json={
            "year": configuration.year,
            "make": configuration.make,
            "model": configuration.model,
            "configuration": (configuration.configuration),
            "source": configuration.source,
            "source_id": configuration.source_id,
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["make"] == "Toyota"
    assert body["model"] == "Camry"

    assert body["specification"] == {
        "powertrain": "gasoline",
        "fuel_grade": "regular",
        "combined_mpg": "32.125",
        "city_mpg": "28.5",
        "highway_mpg": "38.25",
    }


def test_create_rejects_client_supplied_efficiency() -> None:
    user_id = UserId(value=uuid4())

    configuration = _configuration()

    response = _client(
        user_id=user_id,
        repository=FakeSavedVehicleRepository(),
        provider=FakeVehicleSpecificationProvider(
            VehicleSpecificationLookupResult(
                specification=(_gasoline_specification()),
                unavailable_reason=None,
            )
        ),
    ).post(
        "/api/v2/vehicles",
        json={
            "year": configuration.year,
            "make": configuration.make,
            "model": configuration.model,
            "configuration": (configuration.configuration),
            "source": configuration.source,
            "source_id": configuration.source_id,
            "combined_mpg": "999",
        },
    )

    assert response.status_code == 422


def test_create_rejects_client_supplied_user_id() -> None:
    user_id = UserId(value=uuid4())

    configuration = _configuration()

    response = _client(
        user_id=user_id,
        repository=FakeSavedVehicleRepository(),
        provider=FakeVehicleSpecificationProvider(
            VehicleSpecificationLookupResult(
                specification=(_gasoline_specification()),
                unavailable_reason=None,
            )
        ),
    ).post(
        "/api/v2/vehicles",
        json={
            "user_id": str(uuid4()),
            "year": configuration.year,
            "make": configuration.make,
            "model": configuration.model,
            "configuration": (configuration.configuration),
            "source": configuration.source,
            "source_id": configuration.source_id,
        },
    )

    assert response.status_code == 422


def test_create_missing_catalog_configuration_returns_404() -> None:
    user_id = UserId(value=uuid4())

    configuration = _configuration()

    response = _client(
        user_id=user_id,
        repository=FakeSavedVehicleRepository(),
        provider=FakeVehicleSpecificationProvider(
            VehicleSpecificationLookupResult(
                specification=(_gasoline_specification()),
                unavailable_reason=None,
            )
        ),
    ).post(
        "/api/v2/vehicles",
        json={
            "year": 2024,
            "make": configuration.make,
            "model": configuration.model,
            "configuration": (configuration.configuration),
            "source": configuration.source,
            "source_id": configuration.source_id,
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == ("vehicle_configuration_not_found")


def test_create_unsupported_specification_returns_409() -> None:
    user_id = UserId(value=uuid4())

    configuration = _configuration()

    response = _client(
        user_id=user_id,
        repository=FakeSavedVehicleRepository(),
        provider=FakeVehicleSpecificationProvider(
            VehicleSpecificationLookupResult(
                specification=None,
                unavailable_reason=(VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN),
            )
        ),
    ).post(
        "/api/v2/vehicles",
        json={
            "year": configuration.year,
            "make": configuration.make,
            "model": configuration.model,
            "configuration": (configuration.configuration),
            "source": configuration.source,
            "source_id": configuration.source_id,
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == ("vehicle_specification_unavailable")


def test_get_and_delete_saved_vehicle_are_owner_scoped() -> None:
    owner = UserId(value=uuid4())

    repository = FakeSavedVehicleRepository()

    vehicle = repository.create_vehicle(
        owner,
        SavedVehicleSnapshot(
            configuration=_configuration(),
            specification=(_gasoline_specification()),
            specification_retrieved_at=(_RETRIEVED_AT),
        ),
    )

    provider = FakeVehicleSpecificationProvider(
        VehicleSpecificationLookupResult(
            specification=(_gasoline_specification()),
            unavailable_reason=None,
        )
    )

    owner_client = _client(
        user_id=owner,
        repository=repository,
        provider=provider,
    )

    other_client = _client(
        user_id=UserId(value=uuid4()),
        repository=repository,
        provider=provider,
    )

    path = f"/api/v2/vehicles/{vehicle.id.value}"

    assert owner_client.get(path).status_code == 200

    hidden = other_client.get(path)

    assert hidden.status_code == 404
    assert hidden.json()["code"] == ("saved_vehicle_not_found")

    assert other_client.delete(path).status_code == 404

    assert owner_client.delete(path).status_code == 204

    assert owner_client.get(path).status_code == 404


def test_saved_vehicle_response_supports_bev() -> None:
    user_id = UserId(value=uuid4())

    configuration = _configuration()

    response = _client(
        user_id=user_id,
        repository=FakeSavedVehicleRepository(),
        provider=FakeVehicleSpecificationProvider(
            VehicleSpecificationLookupResult(
                specification=(
                    ElectricVehicleSpecification(
                        combined_kwh_per_mile=(Decimal("0.285")),
                        city_kwh_per_mile=(Decimal("0.250")),
                        highway_kwh_per_mile=(Decimal("0.320")),
                    )
                ),
                unavailable_reason=None,
            )
        ),
    ).post(
        "/api/v2/vehicles",
        json={
            "year": configuration.year,
            "make": configuration.make,
            "model": configuration.model,
            "configuration": (configuration.configuration),
            "source": configuration.source,
            "source_id": configuration.source_id,
        },
    )

    assert response.status_code == 201

    assert response.json()["specification"] == {
        "powertrain": "bev",
        "combined_kwh_per_mile": "0.285",
        "city_kwh_per_mile": "0.250",
        "highway_kwh_per_mile": "0.320",
    }
