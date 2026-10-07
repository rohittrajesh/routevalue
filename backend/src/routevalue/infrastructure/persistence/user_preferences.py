"""PostgreSQL persistence for RouteValue user preferences."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Engine

from routevalue.application.preferences import UserPreferences
from routevalue.domain.identity import UserId
from routevalue.infrastructure.persistence.schema import (
    user_preferences,
)


class UserPreferencesPersistenceError(RuntimeError):
    """Persisted preference state violated a RouteValue invariant."""


class PostgresUserPreferencesRepository:
    """Persist user preferences using PostgreSQL upserts."""

    def __init__(
        self,
        *,
        engine: Engine,
    ) -> None:
        self._engine = engine

    def get_preferences(
        self,
        user_id: UserId,
    ) -> UserPreferences:
        """Return persisted preferences or the unset preference state."""

        with self._engine.connect() as connection:
            stored_value = connection.execute(
                select(user_preferences.c.value_of_time_per_hour).where(
                    user_preferences.c.user_id == user_id.value
                )
            ).scalar_one_or_none()

        return UserPreferences(
            value_of_time_per_hour=_validated_value_of_time(stored_value),
        )

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        """Atomically insert or update the user's complete preference state."""

        statement = (
            postgresql_insert(user_preferences)
            .values(
                user_id=user_id.value,
                value_of_time_per_hour=(preferences.value_of_time_per_hour),
            )
            .on_conflict_do_update(
                index_elements=[user_preferences.c.user_id],
                set_={
                    "value_of_time_per_hour": (preferences.value_of_time_per_hour),
                    "updated_at": func.clock_timestamp(),
                },
            )
            .returning(user_preferences.c.value_of_time_per_hour)
        )

        with self._engine.begin() as connection:
            stored_value = connection.execute(statement).scalar_one()

        return UserPreferences(
            value_of_time_per_hour=_validated_value_of_time(stored_value),
        )


def _validated_value_of_time(
    value: object,
) -> Decimal | None:
    """Validate the Decimal-compatible value returned by PostgreSQL."""

    if value is None:
        return None

    if not isinstance(value, Decimal):
        raise UserPreferencesPersistenceError("stored value of time is not a Decimal")

    return value
