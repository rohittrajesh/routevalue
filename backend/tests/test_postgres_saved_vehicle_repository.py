"""Integration tests for PostgreSQL saved-vehicle persistence."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from routevalue.application.models import (
    VehicleCatalogConfiguration,
)
from routevalue.application.ports import (
    SavedVehicleRepository,
)
from routevalue.application.saved_vehicles import (
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
from routevalue.infrastructure.persistence.saved_vehicles import (
    PostgresSavedVehicleRepository,
)
from routevalue.infrastructure.persistence.schema import (
    user_preferences,
    users,
)

_RETRIEVED_AT = datetime(
    2026,
    10,
    7,
    19,
    0,
    tzinfo=UTC,
)


def _repository(
    engine: Engine,
) -> SavedVehicleRepository:
    return PostgresSavedVehicleRepository(
        engine=engine,
    )


def _create_user(
    engine: Engine,
) -> UserId:
    user_id = UserId(value=uuid4())

    with engine.begin() as connection:
        connection.execute(insert(users).values(id=user_id.value))

    return user_id


def _delete_user(
    engine: Engine,
    user_id: UserId,
) -> None:
    with engine.begin() as connection:
        connection.execute(delete(users).where(users.c.id == user_id.value))


def _configuration(
    *,
    source_id: str = "12345",
    configuration: str = "2.5L 4cyl CVT (FWD)",
) -> VehicleCatalogConfiguration:
    return VehicleCatalogConfiguration(
        year=2025,
        make="Toyota",
        model="Camry",
        configuration=configuration,
        source="fueleconomy_gov",
        source_id=source_id,
    )


def _gasoline_snapshot(
    *,
    configuration: (VehicleCatalogConfiguration | None) = None,
) -> SavedVehicleSnapshot:
    return SavedVehicleSnapshot(
        configuration=(configuration or _configuration()),
        specification=(
            GasolineVehicleSpecification(
                combined_mpg=Decimal("32.123456789"),
                city_mpg=Decimal("28.500000001"),
                highway_mpg=Decimal("38.250000009"),
                fuel_grade=(GasolineGrade.REGULAR),
            )
        ),
        specification_retrieved_at=(_RETRIEVED_AT),
    )


def _electric_snapshot() -> SavedVehicleSnapshot:
    return SavedVehicleSnapshot(
        configuration=(
            VehicleCatalogConfiguration(
                year=2025,
                make="Hyundai",
                model="Ioniq 5",
                configuration=("Long Range AWD"),
                source="fueleconomy_gov",
                source_id="bev-67890",
            )
        ),
        specification=(
            ElectricVehicleSpecification(
                combined_kwh_per_mile=(Decimal("0.289375001")),
                city_kwh_per_mile=(Decimal("0.251250002")),
                highway_kwh_per_mile=(Decimal("0.321875003")),
            )
        ),
        specification_retrieved_at=(_RETRIEVED_AT),
    )


def test_repository_round_trips_gasoline_snapshot_exactly(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    snapshot = _gasoline_snapshot()

    try:
        created = repository.create_vehicle(
            user_id,
            snapshot,
        )

        assert isinstance(
            created.id,
            SavedVehicleId,
        )

        assert created.configuration == snapshot.configuration

        assert created.specification == snapshot.specification

        assert created.specification_retrieved_at == _RETRIEVED_AT

        assert created.saved_at.tzinfo is not None
        assert created.saved_at.utcoffset() is not None

        reloaded = repository.get_vehicle(
            user_id,
            created.id,
        )

        assert reloaded == created

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_repository_preserves_optional_gasoline_efficiency_nulls(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    snapshot = SavedVehicleSnapshot(
        configuration=_configuration(),
        specification=(
            GasolineVehicleSpecification(
                combined_mpg=Decimal("31.75"),
                city_mpg=None,
                highway_mpg=None,
                fuel_grade=(GasolineGrade.PREMIUM),
            )
        ),
        specification_retrieved_at=(_RETRIEVED_AT),
    )

    try:
        created = repository.create_vehicle(
            user_id,
            snapshot,
        )

        assert created.specification == snapshot.specification

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_repository_round_trips_bev_snapshot_exactly(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    snapshot = _electric_snapshot()

    try:
        created = repository.create_vehicle(
            user_id,
            snapshot,
        )

        assert created.configuration == snapshot.configuration

        assert created.specification == snapshot.specification

        reloaded = repository.get_vehicle(
            user_id,
            created.id,
        )

        assert reloaded == created

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_list_is_owner_scoped_and_deterministic(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    owner = _create_user(postgres_engine)
    other_user = _create_user(postgres_engine)

    try:
        first = repository.create_vehicle(
            owner,
            _gasoline_snapshot(),
        )

        second_configuration = replace(
            _configuration(),
            configuration="Hybrid eCVT",
            source_id="54321",
        )

        second = repository.create_vehicle(
            owner,
            _gasoline_snapshot(configuration=(second_configuration)),
        )

        _ = repository.create_vehicle(
            other_user,
            _electric_snapshot(),
        )

        first_listing = tuple(repository.list_vehicles(owner))

        second_listing = tuple(repository.list_vehicles(owner))

        assert first_listing == second_listing

        assert {vehicle.id for vehicle in first_listing} == {
            first.id,
            second.id,
        }

        assert all(vehicle not in repository.list_vehicles(other_user) for vehicle in first_listing)

        expected_order = tuple(
            sorted(
                (
                    first,
                    second,
                ),
                key=lambda vehicle: (
                    vehicle.saved_at,
                    vehicle.id.value,
                ),
            )
        )

        assert first_listing == expected_order

    finally:
        _delete_user(
            postgres_engine,
            owner,
        )

        _delete_user(
            postgres_engine,
            other_user,
        )


def test_get_vehicle_cannot_cross_user_boundary(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    owner = _create_user(postgres_engine)
    other_user = _create_user(postgres_engine)

    try:
        created = repository.create_vehicle(
            owner,
            _gasoline_snapshot(),
        )

        assert (
            repository.get_vehicle(
                owner,
                created.id,
            )
            == created
        )

        assert (
            repository.get_vehicle(
                other_user,
                created.id,
            )
            is None
        )

    finally:
        _delete_user(
            postgres_engine,
            owner,
        )

        _delete_user(
            postgres_engine,
            other_user,
        )


def test_delete_vehicle_cannot_cross_user_boundary(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    owner = _create_user(postgres_engine)
    other_user = _create_user(postgres_engine)

    try:
        created = repository.create_vehicle(
            owner,
            _gasoline_snapshot(),
        )

        assert (
            repository.delete_vehicle(
                other_user,
                created.id,
            )
            is False
        )

        assert (
            repository.get_vehicle(
                owner,
                created.id,
            )
            == created
        )

        assert (
            repository.delete_vehicle(
                owner,
                created.id,
            )
            is True
        )

        assert (
            repository.get_vehicle(
                owner,
                created.id,
            )
            is None
        )

    finally:
        _delete_user(
            postgres_engine,
            owner,
        )

        _delete_user(
            postgres_engine,
            other_user,
        )


def test_delete_missing_vehicle_returns_false(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    try:
        deleted = repository.delete_vehicle(
            user_id,
            SavedVehicleId(value=uuid4()),
        )

        assert deleted is False

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_create_vehicle_requires_existing_owner(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    missing_user = UserId(value=uuid4())

    with pytest.raises(IntegrityError):
        repository.create_vehicle(
            missing_user,
            _gasoline_snapshot(),
        )


def test_deleting_default_vehicle_clears_preference_without_losing_value_of_time(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    try:
        vehicle = repository.create_vehicle(
            user_id,
            _gasoline_snapshot(),
        )

        with postgres_engine.begin() as connection:
            connection.execute(
                insert(user_preferences).values(
                    user_id=user_id.value,
                    value_of_time_per_hour=Decimal("37.50"),
                    default_vehicle_id=(vehicle.id.value),
                )
            )

        assert repository.delete_vehicle(
            user_id,
            vehicle.id,
        )

        with postgres_engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        user_preferences.c.value_of_time_per_hour,
                        user_preferences.c.default_vehicle_id,
                    ).where(user_preferences.c.user_id == user_id.value)
                )
                .mappings()
                .one()
            )

        assert row["value_of_time_per_hour"] == Decimal("37.50")

        assert row["default_vehicle_id"] is None

        assert (
            repository.get_vehicle(
                user_id,
                vehicle.id,
            )
            is None
        )

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )
