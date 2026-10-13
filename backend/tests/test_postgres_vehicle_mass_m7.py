"""M7 PostgreSQL integration tests for vehicle mass persistence."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from routevalue.application.models import VehicleCatalogConfiguration
from routevalue.application.saved_vehicles import SavedVehicleSnapshot
from routevalue.domain.identity import UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource
from routevalue.infrastructure.persistence.saved_vehicles import (
    PostgresSavedVehicleRepository,
)
from routevalue.infrastructure.persistence.schema import saved_vehicles, users


def _configuration() -> VehicleCatalogConfiguration:
    return VehicleCatalogConfiguration(
        year=2026,
        make="Test",
        model="Mass Integration Vehicle",
        configuration="Standard",
        source="test",
        source_id="m7-mass-test",
    )


def _snapshot(
    powertrain: str,
    mass: VehicleMass | None,
) -> SavedVehicleSnapshot:
    specification: GasolineVehicleSpecification | ElectricVehicleSpecification

    if powertrain == "gasoline":
        specification = GasolineVehicleSpecification(
            combined_mpg=Decimal("30.125"),
            fuel_grade=GasolineGrade.REGULAR,
            vehicle_mass=mass,
        )
    elif powertrain == "bev":
        specification = ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.29125"),
            vehicle_mass=mass,
        )
    else:
        raise ValueError("unsupported test powertrain")

    return SavedVehicleSnapshot(
        configuration=_configuration(),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 13, tzinfo=UTC),
    )


def _insert_test_user(engine: Engine) -> UserId:
    user = UserId(value=uuid4())

    with engine.begin() as connection:
        connection.execute(insert(users).values(id=user.value))

    return user


def _delete_test_user(engine: Engine, user: UserId) -> None:
    with engine.begin() as connection:
        connection.execute(delete(users).where(users.c.id == user.value))


@pytest.mark.parametrize("powertrain", ["gasoline", "bev"])
def test_repository_round_trips_mass_and_provenance(
    postgres_engine: Engine,
    powertrain: str,
) -> None:
    repository = PostgresSavedVehicleRepository(engine=postgres_engine)
    user = _insert_test_user(postgres_engine)

    mass = VehicleMass(
        kilograms=Decimal("1825.75"),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        source_reference="manufacturer-record-123",
    )
    snapshot = _snapshot(powertrain, mass)

    try:
        created = repository.create_vehicle(user, snapshot)

        assert created.specification == snapshot.specification
        assert created.specification.vehicle_mass == mass

        loaded = repository.get_vehicle(user, created.id)

        assert loaded == created
        assert loaded is not None
        assert loaded.specification.vehicle_mass == mass

        with postgres_engine.connect() as connection:
            row = (
                connection.execute(
                    select(saved_vehicles).where(saved_vehicles.c.id == created.id.value)
                )
                .mappings()
                .one()
            )

        assert row["vehicle_mass_kg"] == Decimal("1825.75")
        assert row["vehicle_mass_source"] == "manufacturer_curb_weight"
        assert row["vehicle_mass_reference"] == "manufacturer-record-123"

    finally:
        _delete_test_user(postgres_engine, user)


@pytest.mark.parametrize("powertrain", ["gasoline", "bev"])
def test_legacy_vehicle_without_mass_remains_readable(
    postgres_engine: Engine,
    powertrain: str,
) -> None:
    repository = PostgresSavedVehicleRepository(engine=postgres_engine)
    user = _insert_test_user(postgres_engine)

    try:
        created = repository.create_vehicle(
            user,
            _snapshot(powertrain, None),
        )

        loaded = repository.get_vehicle(user, created.id)

        assert loaded is not None
        assert loaded.specification.vehicle_mass is None

        with postgres_engine.connect() as connection:
            row = (
                connection.execute(
                    select(saved_vehicles).where(saved_vehicles.c.id == created.id.value)
                )
                .mappings()
                .one()
            )

        assert row["vehicle_mass_kg"] is None
        assert row["vehicle_mass_source"] is None
        assert row["vehicle_mass_reference"] is None

    finally:
        _delete_test_user(postgres_engine, user)


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"vehicle_mass_kg": Decimal(-1)},
        {"vehicle_mass_kg": Decimal(0)},
        {"vehicle_mass_kg": Decimal(1500)},
        {"vehicle_mass_source": "user_provided"},
        {
            "vehicle_mass_kg": Decimal(1500),
            "vehicle_mass_source": "unknown",
        },
        {"vehicle_mass_reference": "orphan-reference"},
        {
            "vehicle_mass_kg": Decimal(1500),
            "vehicle_mass_source": "user_provided",
            "vehicle_mass_reference": " ",
        },
    ],
)
def test_database_rejects_invalid_mass(
    db_connection: Connection,
    invalid_fields: dict[str, object],
) -> None:
    user_id = uuid4()

    db_connection.execute(insert(users).values(id=user_id))

    values: dict[str, object] = {
        "id": uuid4(),
        "user_id": user_id,
        "year": 2026,
        "make": "Test",
        "model": "Invalid Mass",
        "configuration": "Standard",
        "source": "test",
        "source_id": "invalid-mass",
        "specification_retrieved_at": datetime(2026, 10, 13, tzinfo=UTC),
        "powertrain": "gasoline",
        "gasoline_grade": "regular",
        "combined_mpg": Decimal(30),
    }
    values.update(invalid_fields)

    with pytest.raises(IntegrityError), db_connection.begin_nested():
        db_connection.execute(insert(saved_vehicles).values(**values))
