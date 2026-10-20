"""PostgreSQL persistence for RouteValue user preferences."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Engine, RowMapping

from routevalue.application.preferences import (
    PreferredFuelMarket,
    UserPreferences,
    UserPreferencesPatch,
)
from routevalue.application.user_preferences import DefaultVehicleUnavailableError
from routevalue.domain.identity import (
    SavedVehicleId,
    UserId,
)
from routevalue.infrastructure.persistence.schema import (
    saved_vehicles,
    user_preferences,
    users,
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
            row = (
                connection.execute(
                    select(user_preferences).where(user_preferences.c.user_id == user_id.value)
                )
                .mappings()
                .one_or_none()
            )

        if row is None:
            return UserPreferences()

        return _preferences_from_row(row)

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        """Atomically insert or update the user's complete preference state."""

        changes: UserPreferencesPatch = {
            "value_of_time_per_hour": preferences.value_of_time_per_hour,
            "default_vehicle_id": preferences.default_vehicle_id,
            "electricity_price_per_kwh": preferences.electricity_price_per_kwh,
            "preferred_fuel_market": preferences.preferred_fuel_market,
        }
        return self._write_preferences(user_id, changes, validate_default=False)

    def update_preferences(self, user_id: UserId, changes: UserPreferencesPatch) -> UserPreferences:
        """Apply explicit fields in one transaction, including ownership validation."""

        UserPreferences(**changes)
        if not changes:
            raise ValueError("preference update must contain at least one field")
        return self._write_preferences(user_id, changes, validate_default=True)

    def _write_preferences(
        self, user_id: UserId, changes: UserPreferencesPatch, *, validate_default: bool
    ) -> UserPreferences:
        values: dict[str, object] = {}
        if "value_of_time_per_hour" in changes:
            values["value_of_time_per_hour"] = changes["value_of_time_per_hour"]
        if "electricity_price_per_kwh" in changes:
            values["electricity_price_per_kwh"] = changes["electricity_price_per_kwh"]
        if "default_vehicle_id" in changes:
            vehicle = changes["default_vehicle_id"]
            values["default_vehicle_id"] = vehicle.value if vehicle is not None else None
        if "preferred_fuel_market" in changes:
            market = changes["preferred_fuel_market"]
            values.update(
                fuel_market_name=market.display_name if market is not None else None,
                fuel_market_latitude=market.latitude if market is not None else None,
                fuel_market_longitude=market.longitude if market is not None else None,
            )
        statement = (
            postgresql_insert(user_preferences)
            .values(user_id=user_id.value, **values)
            .on_conflict_do_update(
                index_elements=[user_preferences.c.user_id],
                set_={**values, "updated_at": func.clock_timestamp()},
                where=or_(
                    *(
                        user_preferences.c[name].is_distinct_from(value)
                        for name, value in values.items()
                    )
                ),
            )
            .returning(user_preferences)
        )
        with self._engine.begin() as connection:
            # The same owner lock is acquired before default deletion. It covers
            # first writes (no preference row yet) and closes validation/delete races.
            connection.execute(
                select(users.c.id).where(users.c.id == user_id.value).with_for_update()
            ).scalar_one_or_none()
            vehicle_id = changes.get("default_vehicle_id")
            if validate_default and vehicle_id is not None:
                owned = connection.execute(
                    select(saved_vehicles.c.id).where(
                        saved_vehicles.c.user_id == user_id.value,
                        saved_vehicles.c.id == vehicle_id.value,
                    )
                ).scalar_one_or_none()
                if owned is None:
                    raise DefaultVehicleUnavailableError("default vehicle is unavailable")
            row = connection.execute(statement).mappings().one_or_none()
            if row is None:
                row = (
                    connection.execute(
                        select(user_preferences).where(user_preferences.c.user_id == user_id.value)
                    )
                    .mappings()
                    .one()
                )
            return _preferences_from_row(row)


def _validated_value_of_time(
    value: object,
) -> Decimal | None:
    """Validate the Decimal-compatible value returned by PostgreSQL."""

    if value is None:
        return None

    if not isinstance(
        value,
        Decimal,
    ):
        raise UserPreferencesPersistenceError("stored value of time is not a Decimal")

    return value


def _validated_default_vehicle_id(
    value: object,
) -> SavedVehicleId | None:
    """Validate a persisted default saved-vehicle identifier."""

    if value is None:
        return None

    if not isinstance(
        value,
        UUID,
    ):
        raise UserPreferencesPersistenceError("stored default vehicle id is not a UUID")

    return SavedVehicleId(value=value)


def _preferences_from_row(row: RowMapping) -> UserPreferences:
    name = row["fuel_market_name"]
    latitude = row["fuel_market_latitude"]
    longitude = row["fuel_market_longitude"]
    market = None
    if name is not None or latitude is not None or longitude is not None:
        if (
            not isinstance(name, str)
            or not isinstance(latitude, float)
            or not isinstance(longitude, float)
        ):
            raise UserPreferencesPersistenceError("stored fuel market is incomplete or invalid")
        try:
            market = PreferredFuelMarket(name, latitude, longitude)
        except (TypeError, ValueError):
            raise UserPreferencesPersistenceError("stored fuel market is invalid") from None
    return UserPreferences(
        value_of_time_per_hour=_validated_value_of_time(row["value_of_time_per_hour"]),
        default_vehicle_id=_validated_default_vehicle_id(row["default_vehicle_id"]),
        electricity_price_per_kwh=_validated_value_of_time(row["electricity_price_per_kwh"]),
        preferred_fuel_market=market,
    )
