"""M7 mass persistence mapping and schema invariants."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.engine import RowMapping

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
    SavedVehiclePersistenceError,
    _row_to_mass,
    _snapshot_values,
)
from routevalue.infrastructure.persistence.schema import saved_vehicles


def _snapshot(
    specification: (GasolineVehicleSpecification | ElectricVehicleSpecification),
) -> SavedVehicleSnapshot:
    return SavedVehicleSnapshot(
        configuration=VehicleCatalogConfiguration(
            year=2026,
            make="Test",
            model="Vehicle",
            configuration="Standard",
            source="test",
            source_id="123",
        ),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 13, tzinfo=UTC),
    )


def _row(
    kilograms: object,
    source: object,
    reference: object,
) -> RowMapping:
    return cast(
        RowMapping,
        {
            "vehicle_mass_kg": kilograms,
            "vehicle_mass_source": source,
            "vehicle_mass_reference": reference,
        },
    )


@pytest.mark.parametrize(
    "powertrain",
    ["gasoline", "bev"],
)
def test_mass_persists_for_both_powertrains(powertrain: str) -> None:
    mass = VehicleMass(
        kilograms=Decimal("1825.75"),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        source_reference="record-123",
    )

    specification: GasolineVehicleSpecification | ElectricVehicleSpecification

    if powertrain == "gasoline":
        specification = GasolineVehicleSpecification(
            combined_mpg=Decimal(30),
            fuel_grade=GasolineGrade.REGULAR,
            vehicle_mass=mass,
        )
    else:
        specification = ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.3"),
            vehicle_mass=mass,
        )

    values = _snapshot_values(
        user_id=UserId(value=uuid4()),
        snapshot=_snapshot(specification),
    )

    assert values["vehicle_mass_kg"] == mass.kilograms
    assert values["vehicle_mass_source"] == mass.source.value
    assert values["vehicle_mass_reference"] == mass.source_reference

    reconstructed = _row_to_mass(
        _row(
            values["vehicle_mass_kg"],
            values["vehicle_mass_source"],
            values["vehicle_mass_reference"],
        )
    )

    assert reconstructed == mass


def test_legacy_missing_mass_round_trips_as_none() -> None:
    specification = GasolineVehicleSpecification(
        combined_mpg=Decimal(28),
        fuel_grade=GasolineGrade.PREMIUM,
    )

    values = _snapshot_values(
        user_id=UserId(value=uuid4()),
        snapshot=_snapshot(specification),
    )

    assert values["vehicle_mass_kg"] is None
    assert values["vehicle_mass_source"] is None
    assert values["vehicle_mass_reference"] is None

    assert _row_to_mass(_row(None, None, None)) is None


@pytest.mark.parametrize(
    ("kilograms", "source", "reference"),
    [
        (None, "epa_test_weight", None),
        (None, None, "reference"),
        (Decimal(1500), None, None),
        (Decimal(-1), "user_provided", None),
        (Decimal(1500), "invalid", None),
        (Decimal(1500), "user_provided", " "),
        ("1500", "user_provided", None),
    ],
)
def test_invalid_persisted_mass_fails_closed(
    kilograms: object,
    source: object,
    reference: object,
) -> None:
    with pytest.raises(SavedVehiclePersistenceError):
        _row_to_mass(_row(kilograms, source, reference))


def test_schema_matches_migration_columns_and_constraints() -> None:
    columns = saved_vehicles.c

    assert "vehicle_mass_kg" in columns
    assert "vehicle_mass_source" in columns
    assert "vehicle_mass_reference" in columns

    assert columns.vehicle_mass_kg.nullable
    assert columns.vehicle_mass_source.nullable
    assert columns.vehicle_mass_reference.nullable

    names = {constraint.name for constraint in saved_vehicles.constraints}

    assert {
        "ck_saved_vehicles_positive_mass",
        "ck_saved_vehicles_mass_presence",
        "ck_saved_vehicles_mass_source",
        "ck_saved_vehicles_mass_reference",
    } <= names
