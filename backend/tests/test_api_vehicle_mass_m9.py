"""Network-free M9 tests for authenticated saved-vehicle mass updates."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.vehicle_mass import (
    VehicleMassUpdateRequest,
    get_user_vehicle_mass_service,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.models import VehicleCatalogConfiguration
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.application.vehicle_mass_update import UserVehicleMassService
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
)
from routevalue.domain.vehicle_mass import (
    VehicleMass,
    VehicleMassSource,
    pounds_to_kilograms,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    PostgresSavedVehicleRepository,
)
from routevalue.main import create_app


def _vehicle(*, electric: bool = False) -> SavedVehicle:
    specification = (
        ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.286981"),
        )
        if electric
        else GasolineVehicleSpecification(
            combined_mpg=Decimal(28),
            fuel_grade=GasolineGrade.REGULAR,
        )
    )

    return SavedVehicle(
        id=SavedVehicleId(value=uuid4()),
        configuration=VehicleCatalogConfiguration(
            year=2024,
            make="Tesla" if electric else "Toyota",
            model="Model Y" if electric else "Camry",
            configuration="Long Range AWD" if electric else "2.5L AWD",
            source="fueleconomy_gov",
            source_id="12345",
        ),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 16, tzinfo=UTC),
        saved_at=datetime(2026, 10, 16, tzinfo=UTC),
    )


class MemoryVehicleMassRepository:
    """Simple owner-scoped mass persistence fake."""

    def __init__(self, owner: UserId, vehicle: SavedVehicle) -> None:
        self.owner = owner
        self.vehicle = vehicle

    def update_vehicle_mass(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
        mass: VehicleMass | None,
    ) -> SavedVehicle | None:
        if user_id != self.owner or vehicle_id != self.vehicle.id:
            return None

        self.vehicle = replace(
            self.vehicle,
            specification=replace(
                self.vehicle.specification,
                vehicle_mass=mass,
            ),
        )
        return self.vehicle


def _client(
    user: UserId,
    repository: MemoryVehicleMassRepository,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user)
    app.dependency_overrides[get_user_vehicle_mass_service] = lambda: UserVehicleMassService(
        repository=repository
    )
    return TestClient(app)


def test_mass_conversion_preserves_decimal_precision() -> None:
    pounds = Decimal("3875.25")
    mass = pounds_to_kilograms(pounds)

    assert mass > Decimal(0)
    assert abs(mass * Decimal("2.2046226218487757") - pounds) < Decimal("0.000000000001")


@pytest.mark.parametrize(
    "request_body",
    [
        {"weight": "-2", "unit": "lb", "source_reference": "manual"},
        {"weight": "NaN", "unit": "kg", "source_reference": "manual"},
        {"weight": "Inf", "unit": "kg", "source_reference": "manual"},
        {"weight": "1", "unit": "kg", "source_reference": "manual"},
        {"weight": "9000", "unit": "kg", "source_reference": "manual"},
        {"weight": "3000", "source_reference": "manual"},
        {"weight": "3000", "unit": "lb"},
        {"weight": "3000", "unit": "lb", "source_reference": "  "},
        {"weight": None, "unit": "lb"},
        {"weight": None, "source_reference": "manual"},
        {"weight": "3000", "unit": "lb", "source_reference": "manual", "mpg": 999},
    ],
)
def test_invalid_mass_requests_are_rejected(
    request_body: dict[str, object],
) -> None:
    user = UserId(value=uuid4())
    vehicle = _vehicle()
    repository = MemoryVehicleMassRepository(user, vehicle)

    response = _client(user, repository).patch(
        f"/api/v2/vehicles/{vehicle.id.value}/mass",
        json=request_body,
    )

    assert response.status_code == 422
    assert repository.vehicle.specification.vehicle_mass is None


@pytest.mark.parametrize("electric", [False, True])
def test_mass_update_preserves_trusted_vehicle_efficiency(electric: bool) -> None:
    user = UserId(value=uuid4())
    vehicle = _vehicle(electric=electric)
    repository = MemoryVehicleMassRepository(user, vehicle)

    response = _client(user, repository).patch(
        f"/api/v2/vehicles/{vehicle.id.value}/mass",
        json={
            "weight": "3900.125",
            "unit": "lb",
            "source_reference": "Published vehicle specifications",
        },
    )

    assert response.status_code == 200

    body = response.json()
    reported_mass = body["vehicle_mass"]

    assert reported_mass["source"] == "user_provided"
    assert reported_mass["source_reference"] == "Published vehicle specifications"

    expected_mass = pounds_to_kilograms(Decimal("3900.125"))
    assert Decimal(reported_mass["kilograms"]) == expected_mass

    assert repository.vehicle.specification.vehicle_mass is not None

    if electric:
        assert body["specification"]["powertrain"] == "bev"
        assert body["specification"]["combined_kwh_per_mile"] == "0.286981"
    else:
        assert body["specification"]["powertrain"] == "gasoline"
        assert body["specification"]["combined_mpg"] == "28"


def test_mass_can_be_cleared_without_deleting_the_vehicle() -> None:
    user = UserId(value=uuid4())
    vehicle = _vehicle()
    repository = MemoryVehicleMassRepository(user, vehicle)
    client = _client(user, repository)
    path = f"/api/v2/vehicles/{vehicle.id.value}/mass"

    first = client.patch(
        path,
        json={
            "weight": "1800",
            "unit": "kg",
            "source_reference": "Owner's manual",
        },
    )

    assert first.status_code == 200
    assert first.json()["vehicle_mass"]["kilograms"] == "1800"

    cleared = client.patch(path, json={"weight": None})

    assert cleared.status_code == 200
    assert cleared.json().get("vehicle_mass") is None
    assert repository.vehicle.specification.vehicle_mass is None
    assert repository.vehicle.id == vehicle.id


def test_other_user_cannot_modify_vehicle_mass() -> None:
    owner = UserId(value=uuid4())
    caller = UserId(value=uuid4())
    vehicle = _vehicle()
    repository = MemoryVehicleMassRepository(owner, vehicle)

    response = _client(caller, repository).patch(
        f"/api/v2/vehicles/{vehicle.id.value}/mass",
        json={
            "weight": "3900",
            "unit": "lb",
            "source_reference": "Published specification",
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "saved_vehicle_not_found"
    assert repository.vehicle.specification.vehicle_mass is None


def test_model_conversion_records_user_provenance() -> None:
    request = VehicleMassUpdateRequest(
        weight=Decimal(1750),
        unit="kg",
        source_reference="  Owner's manual  ",
    )

    mass = request.to_domain_mass()

    assert mass is not None
    assert mass.kilograms == Decimal(1750)
    assert mass.source is VehicleMassSource.USER_PROVIDED
    assert mass.source_reference == "Owner's manual"


def test_persistence_update_filters_by_vehicle_and_owner() -> None:
    engine = MagicMock(spec=Engine)
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = None

    repository = PostgresSavedVehicleRepository(engine=engine)

    user = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())
    mass = VehicleMass(
        kilograms=Decimal(1800),
        source=VehicleMassSource.USER_PROVIDED,
        source_reference="Owner's manual",
    )

    assert repository.update_vehicle_mass(user, vehicle_id, mass) is None

    statement = connection.execute.call_args.args[0]
    compiled = statement.compile()

    sql = str(compiled)
    parameters = compiled.params

    assert "saved_vehicles.user_id" in sql
    assert "saved_vehicles.id" in sql
    assert user.value in parameters.values()
    assert vehicle_id.value in parameters.values()
    assert mass.kilograms in parameters.values()
    assert mass.source.value in parameters.values()

    engine.begin.assert_called_once()
