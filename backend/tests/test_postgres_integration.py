"""Integration tests against an isolated local PostgreSQL database."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import IntegrityError

from routevalue.infrastructure.persistence.connection import (
    create_application_engine,
)
from routevalue.infrastructure.persistence.schema import (
    auth_identities,
    saved_vehicles,
    user_preferences,
    users,
)

_TEST_DATABASE_ENV = "ROUTEVALUE_TEST_DATABASE_URL"
_EXPECTED_REVISION = "7b3c2a91d0ef"


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    """Connect only to the explicitly approved disposable local database."""

    raw_url = os.environ.get(_TEST_DATABASE_ENV)

    if not raw_url:
        pytest.skip("Local PostgreSQL integration tests require ROUTEVALUE_TEST_DATABASE_URL")

    url = make_url(raw_url)

    if (
        url.drivername != "postgresql+psycopg"
        or url.host != "127.0.0.1"
        or url.port != 55432
        or url.database != "routevalue_m3b4"
        or url.username != "routevalue_local"
    ):
        pytest.fail(
            "Integration tests may only use the designated local RouteValue PostgreSQL database"
        )

    engine = create_application_engine(url=url)

    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()

            if revision != _EXPECTED_REVISION:
                pytest.fail(
                    "Local test database must be migrated to the expected RouteValue revision"
                )

        yield engine

    finally:
        engine.dispose()


@pytest.fixture
def db_connection(
    postgres_engine: Engine,
) -> Iterator[Connection]:
    """Provide a transaction that always rolls back after the test."""

    with postgres_engine.connect() as connection:
        transaction = connection.begin()

        try:
            yield connection
        finally:
            if transaction.is_active:
                transaction.rollback()


def _insert_user(connection: Connection) -> UUID:
    """Create one temporary internal RouteValue user."""

    user_id = uuid4()

    connection.execute(insert(users).values(id=user_id))

    return user_id


def _insert_gasoline_vehicle(
    connection: Connection,
    user_id: UUID,
    overrides: dict[str, object] | None = None,
) -> UUID:
    """Insert a normalized gasoline snapshot with optional test overrides."""

    vehicle_id = uuid4()

    values: dict[str, object] = {
        "id": vehicle_id,
        "user_id": user_id,
        "year": 2025,
        "make": "Toyota",
        "model": "Camry",
        "configuration": "Gasoline configuration",
        "source": "fueleconomy.gov",
        "source_id": "test-vehicle-123",
        "specification_retrieved_at": datetime.now(UTC),
        "powertrain": "gasoline",
        "gasoline_grade": "regular",
        "combined_mpg": Decimal("31.123456789"),
        "city_mpg": Decimal("28.5"),
        "highway_mpg": Decimal("36.25"),
    }

    if overrides is not None:
        values.update(overrides)

    connection.execute(insert(saved_vehicles).values(**values))

    return vehicle_id


def test_gasoline_snapshot_preserves_decimal_precision(
    db_connection: Connection,
) -> None:
    user_id = _insert_user(db_connection)

    vehicle_id = _insert_gasoline_vehicle(
        db_connection,
        user_id,
    )

    vehicle = (
        db_connection.execute(select(saved_vehicles).where(saved_vehicles.c.id == vehicle_id))
        .mappings()
        .one()
    )

    assert vehicle["user_id"] == user_id
    assert vehicle["powertrain"] == "gasoline"
    assert vehicle["gasoline_grade"] == "regular"
    assert vehicle["combined_mpg"] == Decimal("31.123456789")
    assert vehicle["city_mpg"] == Decimal("28.5")
    assert vehicle["highway_mpg"] == Decimal("36.25")
    assert vehicle["source"] == "fueleconomy.gov"
    assert vehicle["source_id"] == "test-vehicle-123"
    assert vehicle["combined_kwh_per_mile"] is None


def test_bev_snapshot_preserves_electricity_efficiency(
    db_connection: Connection,
) -> None:
    user_id = _insert_user(db_connection)
    vehicle_id = uuid4()

    db_connection.execute(
        insert(saved_vehicles).values(
            id=vehicle_id,
            user_id=user_id,
            year=2025,
            make="Hyundai",
            model="Ioniq 5",
            configuration="Battery electric configuration",
            source="fueleconomy.gov",
            source_id="test-bev-456",
            specification_retrieved_at=datetime.now(UTC),
            powertrain="bev",
            combined_kwh_per_mile=Decimal("0.289375"),
            city_kwh_per_mile=Decimal("0.25125"),
            highway_kwh_per_mile=Decimal("0.321875"),
        )
    )

    vehicle = (
        db_connection.execute(select(saved_vehicles).where(saved_vehicles.c.id == vehicle_id))
        .mappings()
        .one()
    )

    assert vehicle["powertrain"] == "bev"
    assert vehicle["combined_kwh_per_mile"] == Decimal("0.289375")
    assert vehicle["city_kwh_per_mile"] == Decimal("0.25125")
    assert vehicle["highway_kwh_per_mile"] == Decimal("0.321875")
    assert vehicle["gasoline_grade"] is None
    assert vehicle["combined_mpg"] is None


def test_external_identity_is_unique_per_issuer_and_subject(
    db_connection: Connection,
) -> None:
    first_user = _insert_user(db_connection)
    second_user = _insert_user(db_connection)

    db_connection.execute(
        insert(auth_identities).values(
            id=uuid4(),
            user_id=first_user,
            issuer="https://auth.example.test",
            subject="external-user-123",
        )
    )

    with pytest.raises(IntegrityError), db_connection.begin_nested():
        db_connection.execute(
            insert(auth_identities).values(
                id=uuid4(),
                user_id=second_user,
                issuer="https://auth.example.test",
                subject="external-user-123",
            )
        )

    db_connection.execute(
        insert(auth_identities).values(
            id=uuid4(),
            user_id=second_user,
            issuer="https://another-issuer.example.test",
            subject="external-user-123",
        )
    )


def test_default_vehicle_must_belong_to_same_user(
    db_connection: Connection,
) -> None:
    first_user = _insert_user(db_connection)
    second_user = _insert_user(db_connection)

    first_vehicle = _insert_gasoline_vehicle(
        db_connection,
        first_user,
    )

    with pytest.raises(IntegrityError), db_connection.begin_nested():
        db_connection.execute(
            insert(user_preferences).values(
                user_id=second_user,
                default_vehicle_id=first_vehicle,
            )
        )

    second_vehicle = _insert_gasoline_vehicle(
        db_connection,
        second_user,
    )

    db_connection.execute(
        insert(user_preferences).values(
            user_id=second_user,
            default_vehicle_id=second_vehicle,
        )
    )

    selected = db_connection.execute(
        select(user_preferences.c.default_vehicle_id).where(
            user_preferences.c.user_id == second_user
        )
    ).scalar_one()

    assert selected == second_vehicle


def test_vehicle_requires_existing_owner(
    db_connection: Connection,
) -> None:
    nonexistent_user = uuid4()

    with pytest.raises(IntegrityError), db_connection.begin_nested():
        _insert_gasoline_vehicle(
            db_connection,
            nonexistent_user,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"powertrain": "hybrid"},
        {"gasoline_grade": None},
        {"combined_mpg": None},
        {"combined_mpg": Decimal(-1)},
        {"combined_kwh_per_mile": Decimal("0.25")},
        {"year": 0},
    ],
)
def test_invalid_gasoline_snapshots_are_rejected(
    db_connection: Connection,
    overrides: dict[str, object],
) -> None:
    user_id = _insert_user(db_connection)

    with pytest.raises(IntegrityError), db_connection.begin_nested():
        _insert_gasoline_vehicle(
            db_connection,
            user_id,
            overrides=overrides,
        )


def test_negative_value_of_time_is_rejected(
    db_connection: Connection,
) -> None:
    user_id = _insert_user(db_connection)

    with pytest.raises(IntegrityError), db_connection.begin_nested():
        db_connection.execute(
            insert(user_preferences).values(
                user_id=user_id,
                value_of_time_per_hour=Decimal("-0.01"),
            )
        )


def test_default_vehicle_must_be_cleared_before_deletion(
    db_connection: Connection,
) -> None:
    user_id = _insert_user(db_connection)
    vehicle_id = _insert_gasoline_vehicle(
        db_connection,
        user_id,
    )

    db_connection.execute(
        insert(user_preferences).values(
            user_id=user_id,
            default_vehicle_id=vehicle_id,
            value_of_time_per_hour=Decimal("25.125"),
        )
    )

    with pytest.raises(IntegrityError), db_connection.begin_nested():
        db_connection.execute(delete(saved_vehicles).where(saved_vehicles.c.id == vehicle_id))

    db_connection.execute(
        update(user_preferences)
        .where(user_preferences.c.user_id == user_id)
        .values(default_vehicle_id=None)
    )

    db_connection.execute(delete(saved_vehicles).where(saved_vehicles.c.id == vehicle_id))

    preferences = (
        db_connection.execute(select(user_preferences).where(user_preferences.c.user_id == user_id))
        .mappings()
        .one()
    )

    assert preferences["default_vehicle_id"] is None
    assert preferences["value_of_time_per_hour"] == Decimal("25.125")


def test_transaction_rollback_discards_user(
    postgres_engine: Engine,
) -> None:
    user_id = uuid4()

    with postgres_engine.connect() as connection:
        transaction = connection.begin()

        try:
            connection.execute(insert(users).values(id=user_id))
        finally:
            transaction.rollback()

    with postgres_engine.connect() as connection:
        result = connection.execute(
            select(users.c.id).where(users.c.id == user_id)
        ).scalar_one_or_none()

    assert result is None
