"""PostgreSQL persistence for user-owned saved vehicle snapshots."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Engine, RowMapping

from routevalue.application.models import (
    VehicleCatalogConfiguration,
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
    VehicleEnergySpecification,
)
from routevalue.infrastructure.persistence.schema import (
    saved_vehicles,
    user_preferences,
)


class SavedVehiclePersistenceError(RuntimeError):
    """Persisted saved-vehicle state violated a RouteValue invariant."""


class PostgresSavedVehicleRepository:
    """Persist normalized user-owned vehicle snapshots in PostgreSQL."""

    def __init__(
        self,
        *,
        engine: Engine,
    ) -> None:
        self._engine = engine

    def list_vehicles(
        self,
        user_id: UserId,
    ) -> tuple[SavedVehicle, ...]:
        """Return the user's saved vehicles in deterministic order."""

        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(saved_vehicles)
                    .where(saved_vehicles.c.user_id == user_id.value)
                    .order_by(
                        saved_vehicles.c.saved_at.asc(),
                        saved_vehicles.c.id.asc(),
                    )
                )
                .mappings()
                .all()
            )

        return tuple(_row_to_saved_vehicle(row) for row in rows)

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        """Return one saved vehicle only within the requested owner scope."""

        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(saved_vehicles).where(
                        saved_vehicles.c.user_id == user_id.value,
                        saved_vehicles.c.id == vehicle_id.value,
                    )
                )
                .mappings()
                .one_or_none()
            )

        if row is None:
            return None

        return _row_to_saved_vehicle(row)

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        """Persist one immutable normalized vehicle specification snapshot."""

        values = _snapshot_values(
            user_id=user_id,
            snapshot=snapshot,
        )

        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    insert(saved_vehicles).values(**values).returning(*saved_vehicles.c)
                )
                .mappings()
                .one()
            )

        return _row_to_saved_vehicle(row)

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        """Delete one owned vehicle and safely clear it as the user's default."""

        with self._engine.begin() as connection:
            connection.execute(
                update(user_preferences)
                .where(
                    user_preferences.c.user_id == user_id.value,
                    user_preferences.c.default_vehicle_id == vehicle_id.value,
                )
                .values(
                    default_vehicle_id=None,
                    updated_at=func.clock_timestamp(),
                )
            )

            deleted_id = connection.execute(
                delete(saved_vehicles)
                .where(
                    saved_vehicles.c.user_id == user_id.value,
                    saved_vehicles.c.id == vehicle_id.value,
                )
                .returning(saved_vehicles.c.id)
            ).scalar_one_or_none()

        return deleted_id is not None


def _snapshot_values(
    *,
    user_id: UserId,
    snapshot: SavedVehicleSnapshot,
) -> dict[str, object]:
    """Map one normalized snapshot to its PostgreSQL representation."""

    values: dict[str, object] = {
        "id": uuid4(),
        "user_id": user_id.value,
        "year": snapshot.configuration.year,
        "make": snapshot.configuration.make,
        "model": snapshot.configuration.model,
        "configuration": (snapshot.configuration.configuration),
        "source": snapshot.configuration.source,
        "source_id": snapshot.configuration.source_id,
        "specification_retrieved_at": (snapshot.specification_retrieved_at),
    }

    specification = snapshot.specification

    if isinstance(
        specification,
        GasolineVehicleSpecification,
    ):
        values.update(
            {
                "powertrain": "gasoline",
                "gasoline_grade": (specification.fuel_grade.value),
                "combined_mpg": (specification.combined_mpg),
                "city_mpg": specification.city_mpg,
                "highway_mpg": (specification.highway_mpg),
                "combined_kwh_per_mile": None,
                "city_kwh_per_mile": None,
                "highway_kwh_per_mile": None,
            }
        )

        return values

    if isinstance(
        specification,
        ElectricVehicleSpecification,
    ):
        values.update(
            {
                "powertrain": "bev",
                "gasoline_grade": None,
                "combined_mpg": None,
                "city_mpg": None,
                "highway_mpg": None,
                "combined_kwh_per_mile": (specification.combined_kwh_per_mile),
                "city_kwh_per_mile": (specification.city_kwh_per_mile),
                "highway_kwh_per_mile": (specification.highway_kwh_per_mile),
            }
        )

        return values

    raise SavedVehiclePersistenceError("unsupported saved vehicle specification type")


def _row_to_saved_vehicle(
    row: RowMapping,
) -> SavedVehicle:
    """Reconstruct one provider-neutral saved vehicle from PostgreSQL."""

    vehicle_id = SavedVehicleId(
        value=_require_uuid(
            row["id"],
            field_name="id",
        )
    )

    configuration = VehicleCatalogConfiguration(
        year=_require_int(
            row["year"],
            field_name="year",
        ),
        make=_require_str(
            row["make"],
            field_name="make",
        ),
        model=_require_str(
            row["model"],
            field_name="model",
        ),
        configuration=_require_str(
            row["configuration"],
            field_name="configuration",
        ),
        source=_require_str(
            row["source"],
            field_name="source",
        ),
        source_id=_require_str(
            row["source_id"],
            field_name="source_id",
        ),
    )

    specification = _row_to_specification(row)

    return SavedVehicle(
        id=vehicle_id,
        configuration=configuration,
        specification=specification,
        specification_retrieved_at=(
            _require_datetime(
                row["specification_retrieved_at"],
                field_name=("specification_retrieved_at"),
            )
        ),
        saved_at=_require_datetime(
            row["saved_at"],
            field_name="saved_at",
        ),
    )


def _row_to_specification(
    row: RowMapping,
) -> VehicleEnergySpecification:
    """Reconstruct the correct domain specification for one persisted row."""

    powertrain = _require_str(
        row["powertrain"],
        field_name="powertrain",
    )

    if powertrain == "gasoline":
        grade_value = _require_str(
            row["gasoline_grade"],
            field_name="gasoline_grade",
        )

        try:
            grade = GasolineGrade(grade_value)
        except ValueError as exc:
            raise SavedVehiclePersistenceError("stored gasoline grade is invalid") from exc

        return GasolineVehicleSpecification(
            combined_mpg=_require_decimal(
                row["combined_mpg"],
                field_name="combined_mpg",
            ),
            city_mpg=_optional_decimal(
                row["city_mpg"],
                field_name="city_mpg",
            ),
            highway_mpg=_optional_decimal(
                row["highway_mpg"],
                field_name="highway_mpg",
            ),
            fuel_grade=grade,
        )

    if powertrain == "bev":
        return ElectricVehicleSpecification(
            combined_kwh_per_mile=(
                _require_decimal(
                    row["combined_kwh_per_mile"],
                    field_name=("combined_kwh_per_mile"),
                )
            ),
            city_kwh_per_mile=(
                _optional_decimal(
                    row["city_kwh_per_mile"],
                    field_name=("city_kwh_per_mile"),
                )
            ),
            highway_kwh_per_mile=(
                _optional_decimal(
                    row["highway_kwh_per_mile"],
                    field_name=("highway_kwh_per_mile"),
                )
            ),
        )

    raise SavedVehiclePersistenceError("stored powertrain is unsupported")


def _require_uuid(
    value: object,
    *,
    field_name: str,
) -> UUID:
    if not isinstance(
        value,
        UUID,
    ):
        raise SavedVehiclePersistenceError(f"stored {field_name} is not a UUID")

    return value


def _require_int(
    value: object,
    *,
    field_name: str,
) -> int:
    if not isinstance(
        value,
        int,
    ) or isinstance(
        value,
        bool,
    ):
        raise SavedVehiclePersistenceError(f"stored {field_name} is not an integer")

    return value


def _require_str(
    value: object,
    *,
    field_name: str,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise SavedVehiclePersistenceError(f"stored {field_name} is not a string")

    return value


def _require_decimal(
    value: object,
    *,
    field_name: str,
) -> Decimal:
    if not isinstance(
        value,
        Decimal,
    ):
        raise SavedVehiclePersistenceError(f"stored {field_name} is not a Decimal")

    return value


def _optional_decimal(
    value: object,
    *,
    field_name: str,
) -> Decimal | None:
    if value is None:
        return None

    return _require_decimal(
        value,
        field_name=field_name,
    )


def _require_datetime(
    value: object,
    *,
    field_name: str,
) -> datetime:
    if not isinstance(
        value,
        datetime,
    ):
        raise SavedVehiclePersistenceError(f"stored {field_name} is not a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise SavedVehiclePersistenceError(f"stored {field_name} is not timezone-aware")

    return value
