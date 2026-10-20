"""Offline validation of RouteValue persistence schema and migrations."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.schema import CreateTable

from routevalue.infrastructure.persistence.schema import (
    auth_identities,
    eia_pricing_observations,
    eia_pricing_snapshots,
    eia_refresh_attempts,
    elevation_call_reservations,
    metadata,
    saved_vehicles,
    user_preferences,
    users,
)


def test_only_routevalue_owned_tables_are_registered() -> None:
    assert set(metadata.tables) == {
        "public.users",
        "public.auth_identities",
        "public.user_preferences",
        "public.saved_vehicles",
        "public.eia_pricing_snapshots",
        "public.eia_pricing_observations",
        "public.elevation_call_reservations",
        "public.eia_refresh_attempts",
    }


@pytest.mark.parametrize(
    ("table_name", "key_name"),
    [
        ("public.users", "id"),
        ("public.auth_identities", "id"),
        ("public.saved_vehicles", "id"),
        ("public.user_preferences", "user_id"),
    ],
)
def test_primary_keys_are_internal_uuids(
    table_name: str,
    key_name: str,
) -> None:
    table = metadata.tables[table_name]

    assert [column.name for column in table.primary_key.columns] == [key_name]
    assert isinstance(table.c[key_name].type, Uuid)


def test_identity_linkage_is_unique_per_verified_issuer_and_subject() -> None:
    constraints = [
        constraint
        for constraint in auth_identities.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert any(
        constraint.name == "uq_auth_identities_issuer_subject"
        and [column.name for column in constraint.columns] == ["issuer", "subject"]
        for constraint in constraints
    )

    assert {fk.target_fullname for fk in auth_identities.c.user_id.foreign_keys} == {
        "public.users.id"
    }


def test_vehicle_snapshots_have_provenance_and_both_energy_shapes() -> None:
    assert set(saved_vehicles.c.keys()) >= {
        "user_id",
        "year",
        "make",
        "model",
        "configuration",
        "source",
        "source_id",
        "specification_retrieved_at",
        "powertrain",
        "gasoline_grade",
        "combined_mpg",
        "city_mpg",
        "highway_mpg",
        "combined_kwh_per_mile",
        "city_kwh_per_mile",
        "highway_kwh_per_mile",
    }

    assert saved_vehicles.c.specification_retrieved_at.nullable is False

    assert {fk.target_fullname for fk in saved_vehicles.c.user_id.foreign_keys} == {
        "public.users.id"
    }


@pytest.mark.parametrize(
    "column",
    [
        "combined_mpg",
        "city_mpg",
        "highway_mpg",
        "combined_kwh_per_mile",
        "city_kwh_per_mile",
        "highway_kwh_per_mile",
    ],
)
def test_energy_efficiencies_are_unrounded_decimals(
    column: str,
) -> None:
    data_type = saved_vehicles.c[column].type

    assert isinstance(data_type, Numeric)
    assert data_type.precision is None
    assert data_type.scale is None


def test_user_value_of_time_is_unrounded_optional_decimal() -> None:
    value_of_time = user_preferences.c.value_of_time_per_hour

    assert value_of_time.nullable
    assert isinstance(value_of_time.type, Numeric)
    assert value_of_time.type.precision is None
    assert value_of_time.type.scale is None


def test_default_vehicle_fk_requires_matching_owner() -> None:
    constraints = [
        constraint
        for constraint in user_preferences.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_preferences_default_owned_vehicle"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "default_vehicle_id",
        "user_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "public.saved_vehicles.id",
        "public.saved_vehicles.user_id",
    ]


def test_database_constraints_cover_vehicle_and_preference_validity() -> None:
    vehicle_constraints = {
        constraint.name
        for constraint in saved_vehicles.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_saved_vehicles_powertrain_shape" in vehicle_constraints
    assert "ck_saved_vehicles_gasoline_grade" in vehicle_constraints
    assert "ck_saved_vehicles_valid_year" in vehicle_constraints

    for name in (
        "combined_mpg",
        "city_mpg",
        "highway_mpg",
        "combined_kwh_per_mile",
        "city_kwh_per_mile",
        "highway_kwh_per_mile",
    ):
        assert f"ck_saved_vehicles_positive_{name}" in vehicle_constraints

    assert any(
        constraint.name == "ck_user_preferences_nonnegative_value_of_time"
        for constraint in user_preferences.constraints
        if isinstance(constraint, CheckConstraint)
    )


def test_eia_snapshot_primary_key_is_regional() -> None:
    """Verify regional identity and timezone-aware refresh storage."""
    from sqlalchemy import DateTime

    assert [column.name for column in eia_pricing_snapshots.primary_key.columns] == ["region_id"]

    refreshed_at = eia_pricing_snapshots.c.refreshed_at

    assert refreshed_at.nullable is False
    assert isinstance(refreshed_at.type, DateTime)
    assert refreshed_at.type.timezone is True


def test_eia_observation_primary_key_is_region_and_grade() -> None:
    assert [column.name for column in eia_pricing_observations.primary_key.columns] == [
        "region_id",
        "fuel_grade",
    ]


def test_eia_observation_price_is_unrounded_decimal() -> None:
    price = eia_pricing_observations.c.price_per_gallon

    assert isinstance(price.type, Numeric)
    assert price.type.precision is None
    assert price.type.scale is None
    assert price.nullable is False


def test_eia_observation_foreign_key_uses_cascade() -> None:
    constraints = [
        constraint
        for constraint in eia_pricing_observations.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]

    assert len(constraints) == 1
    assert constraints[0].ondelete == "CASCADE"

    assert {fk.target_fullname for fk in eia_pricing_observations.c.region_id.foreign_keys} == {
        "public.eia_pricing_snapshots.region_id"
    }


def test_eia_observations_have_unique_series_per_region() -> None:
    constraints = [
        constraint
        for constraint in eia_pricing_observations.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert any(
        constraint.name == "uq_eia_observations_region_series"
        and [column.name for column in constraint.columns] == ["region_id", "series_id"]
        for constraint in constraints
    )


def test_eia_price_database_constraints_are_registered() -> None:
    names = {
        constraint.name
        for constraint in eia_pricing_observations.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_eia_observations_grade" in names
    assert "ck_eia_observations_series_nonblank" in names
    assert "ck_eia_observations_nonnegative_price" in names


def test_generated_ddl_stays_in_public_schema() -> None:
    from sqlalchemy.engine import make_url

    from routevalue.infrastructure.persistence.connection import (
        create_application_engine,
    )

    engine = create_application_engine(
        url=make_url("postgresql+psycopg://routevalue:placeholder@localhost/routevalue")
    )

    try:
        for table in (
            users,
            auth_identities,
            saved_vehicles,
            user_preferences,
            eia_pricing_snapshots,
            eia_refresh_attempts,
            eia_pricing_observations,
            elevation_call_reservations,
            eia_refresh_attempts,
        ):
            sql = str(CreateTable(table).compile(dialect=engine.dialect))

            assert f"CREATE TABLE public.{table.name}" in sql
            assert "neon_auth" not in sql

    finally:
        engine.dispose()


def test_alembic_recognizes_exactly_one_current_head() -> None:
    backend_root = Path(__file__).resolve().parents[1]

    config = Config(str(backend_root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["d41e7a902b63"]
    retry_migration = scripts.get_revision("d41e7a902b63")
    assert retry_migration is not None
    assert retry_migration.down_revision == "a19d6e2c740b"
    preference_migration = scripts.get_revision("a19d6e2c740b")
    assert preference_migration is not None
    assert preference_migration.down_revision == "f2b7c39a106d"
    quota_migration = scripts.get_revision("f2b7c39a106d")
    assert quota_migration is not None
    assert quota_migration.down_revision == "e8a1d4c209bf"

    initial = scripts.get_revision("7b3c2a91d0ef")
    mass_migration = scripts.get_revision("c8e4b72a91d3")
    eia_migration = scripts.get_revision("e8a1d4c209bf")

    assert initial is not None
    assert initial.down_revision is None

    assert mass_migration is not None
    assert mass_migration.down_revision == "7b3c2a91d0ef"

    assert eia_migration is not None
    assert eia_migration.down_revision == "c8e4b72a91d3"
