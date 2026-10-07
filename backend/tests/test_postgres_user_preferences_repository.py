"""Integration tests for PostgreSQL user-preference persistence."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from routevalue.application.ports import UserPreferencesRepository
from routevalue.application.preferences import UserPreferences
from routevalue.domain.identity import UserId
from routevalue.infrastructure.persistence.schema import (
    saved_vehicles,
    user_preferences,
    users,
)
from routevalue.infrastructure.persistence.user_preferences import (
    PostgresUserPreferencesRepository,
)


def _repository(
    engine: Engine,
) -> UserPreferencesRepository:
    return PostgresUserPreferencesRepository(
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


def _create_gasoline_vehicle(
    engine: Engine,
    user_id: UserId,
) -> object:
    vehicle_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            insert(saved_vehicles).values(
                id=vehicle_id,
                user_id=user_id.value,
                year=2025,
                make="Toyota",
                model="Camry",
                configuration="Gasoline configuration",
                source="fueleconomy.gov",
                source_id=f"test-{uuid4().hex}",
                specification_retrieved_at=datetime.now(UTC),
                powertrain="gasoline",
                gasoline_grade="regular",
                combined_mpg=Decimal("32.125"),
                city_mpg=Decimal("28.5"),
                highway_mpg=Decimal("38.25"),
            )
        )

    return vehicle_id


def test_missing_row_returns_unset_preferences_without_creating_row(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    try:
        preferences = repository.get_preferences(user_id)

        assert preferences == UserPreferences()

        with postgres_engine.connect() as connection:
            row_count = connection.execute(
                select(func.count())
                .select_from(user_preferences)
                .where(user_preferences.c.user_id == user_id.value)
            ).scalar_one()

        assert row_count == 0

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_first_save_creates_exact_decimal_preference(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    try:
        saved = repository.save_preferences(
            user_id,
            UserPreferences(value_of_time_per_hour=Decimal("27.123456789")),
        )

        assert saved.value_of_time_per_hour == Decimal("27.123456789")

        reloaded = repository.get_preferences(user_id)

        assert reloaded == saved

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_existing_preference_is_updated_without_duplicate_row(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    try:
        _ = repository.save_preferences(
            user_id,
            UserPreferences(value_of_time_per_hour=Decimal(20)),
        )

        updated = repository.save_preferences(
            user_id,
            UserPreferences(value_of_time_per_hour=Decimal("45.75")),
        )

        assert updated.value_of_time_per_hour == Decimal("45.75")

        with postgres_engine.connect() as connection:
            row_count = connection.execute(
                select(func.count())
                .select_from(user_preferences)
                .where(user_preferences.c.user_id == user_id.value)
            ).scalar_one()

        assert row_count == 1

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_value_of_time_can_be_cleared_back_to_null(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    try:
        _ = repository.save_preferences(
            user_id,
            UserPreferences(value_of_time_per_hour=Decimal(50)),
        )

        cleared = repository.save_preferences(
            user_id,
            UserPreferences(),
        )

        assert cleared.value_of_time_per_hour is None

        assert repository.get_preferences(user_id) == UserPreferences()

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_preferences_remain_isolated_between_users(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    first_user = _create_user(postgres_engine)
    second_user = _create_user(postgres_engine)

    try:
        _ = repository.save_preferences(
            first_user,
            UserPreferences(value_of_time_per_hour=Decimal(15)),
        )

        _ = repository.save_preferences(
            second_user,
            UserPreferences(value_of_time_per_hour=Decimal(90)),
        )

        assert repository.get_preferences(first_user).value_of_time_per_hour == Decimal(15)

        assert repository.get_preferences(second_user).value_of_time_per_hour == Decimal(90)

    finally:
        _delete_user(
            postgres_engine,
            first_user,
        )

        _delete_user(
            postgres_engine,
            second_user,
        )


def test_value_of_time_update_preserves_default_vehicle(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    vehicle_id = _create_gasoline_vehicle(
        postgres_engine,
        user_id,
    )

    try:
        with postgres_engine.begin() as connection:
            connection.execute(
                insert(user_preferences).values(
                    user_id=user_id.value,
                    value_of_time_per_hour=Decimal(10),
                    default_vehicle_id=vehicle_id,
                )
            )

        _ = repository.save_preferences(
            user_id,
            UserPreferences(value_of_time_per_hour=Decimal(30)),
        )

        with postgres_engine.connect() as connection:
            stored_default = connection.execute(
                select(user_preferences.c.default_vehicle_id).where(
                    user_preferences.c.user_id == user_id.value
                )
            ).scalar_one()

        assert stored_default == vehicle_id

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_updated_at_advances_when_preference_changes(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    user_id = _create_user(postgres_engine)

    try:
        _ = repository.save_preferences(
            user_id,
            UserPreferences(value_of_time_per_hour=Decimal(12)),
        )

        with postgres_engine.connect() as connection:
            first_updated_at = connection.execute(
                select(user_preferences.c.updated_at).where(
                    user_preferences.c.user_id == user_id.value
                )
            ).scalar_one()

        _ = repository.save_preferences(
            user_id,
            UserPreferences(value_of_time_per_hour=Decimal(13)),
        )

        with postgres_engine.connect() as connection:
            second_updated_at = connection.execute(
                select(user_preferences.c.updated_at).where(
                    user_preferences.c.user_id == user_id.value
                )
            ).scalar_one()

        assert second_updated_at > first_updated_at

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_preference_row_requires_existing_internal_user(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    nonexistent_user = UserId(value=uuid4())

    with pytest.raises(IntegrityError):
        repository.save_preferences(
            nonexistent_user,
            UserPreferences(value_of_time_per_hour=Decimal(20)),
        )
