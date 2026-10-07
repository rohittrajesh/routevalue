"""SQLAlchemy Core definitions for RouteValue-owned business tables."""

from collections.abc import MutableMapping
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)

metadata = MetaData(schema="public")


users = Table(
    "users",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)


auth_identities = Table(
    "auth_identities",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "user_id",
        Uuid(as_uuid=True),
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("issuer", Text(), nullable=False),
    Column("subject", Text(), nullable=False),
    Column(
        "linked_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint(
        "issuer",
        "subject",
        name="uq_auth_identities_issuer_subject",
    ),
    CheckConstraint(
        "length(btrim(issuer)) > 0 AND length(btrim(subject)) > 0",
        name="ck_auth_identities_nonblank_subject",
    ),
)


saved_vehicles = Table(
    "saved_vehicles",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "user_id",
        Uuid(as_uuid=True),
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("year", Integer(), nullable=False),
    Column("make", Text(), nullable=False),
    Column("model", Text(), nullable=False),
    Column("configuration", Text(), nullable=False),
    Column("source", Text(), nullable=False),
    Column("source_id", Text(), nullable=False),
    Column(
        "specification_retrieved_at",
        DateTime(timezone=True),
        nullable=False,
    ),
    Column("powertrain", String(16), nullable=False),
    Column("gasoline_grade", String(16), nullable=True),
    Column("combined_mpg", Numeric(), nullable=True),
    Column("city_mpg", Numeric(), nullable=True),
    Column("highway_mpg", Numeric(), nullable=True),
    Column("combined_kwh_per_mile", Numeric(), nullable=True),
    Column("city_kwh_per_mile", Numeric(), nullable=True),
    Column("highway_kwh_per_mile", Numeric(), nullable=True),
    Column(
        "saved_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint(
        "id",
        "user_id",
        name="uq_saved_vehicles_id_owner",
    ),
    CheckConstraint(
        "year > 0",
        name="ck_saved_vehicles_valid_year",
    ),
    CheckConstraint(
        "length(btrim(make)) > 0 AND length(btrim(model)) > 0 "
        "AND length(btrim(configuration)) > 0 AND length(btrim(source)) > 0 "
        "AND length(btrim(source_id)) > 0",
        name="ck_saved_vehicles_nonblank_identity",
    ),
    CheckConstraint(
        "gasoline_grade IS NULL OR gasoline_grade IN ('regular', 'midgrade', 'premium')",
        name="ck_saved_vehicles_gasoline_grade",
    ),
    CheckConstraint(
        "(powertrain = 'gasoline' AND gasoline_grade IS NOT NULL "
        "AND combined_mpg IS NOT NULL "
        "AND combined_kwh_per_mile IS NULL AND city_kwh_per_mile IS NULL "
        "AND highway_kwh_per_mile IS NULL) "
        "OR (powertrain = 'bev' AND combined_kwh_per_mile IS NOT NULL "
        "AND gasoline_grade IS NULL AND combined_mpg IS NULL "
        "AND city_mpg IS NULL AND highway_mpg IS NULL)",
        name="ck_saved_vehicles_powertrain_shape",
    ),
    *(
        CheckConstraint(
            f"{name} IS NULL OR {name} > 0",
            name=f"ck_saved_vehicles_positive_{name}",
        )
        for name in (
            "combined_mpg",
            "city_mpg",
            "highway_mpg",
            "combined_kwh_per_mile",
            "city_kwh_per_mile",
            "highway_kwh_per_mile",
        )
    ),
)


user_preferences = Table(
    "user_preferences",
    metadata,
    Column(
        "user_id",
        Uuid(as_uuid=True),
        ForeignKey("public.users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("value_of_time_per_hour", Numeric(), nullable=True),
    Column("default_vehicle_id", Uuid(as_uuid=True), nullable=True),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    ForeignKeyConstraint(
        ["default_vehicle_id", "user_id"],
        ["public.saved_vehicles.id", "public.saved_vehicles.user_id"],
        name="fk_preferences_default_owned_vehicle",
    ),
    CheckConstraint(
        "value_of_time_per_hour IS NULL OR value_of_time_per_hour >= 0",
        name="ck_user_preferences_nonnegative_value_of_time",
    ),
)


Index("ix_auth_identities_user_id", auth_identities.c.user_id)
Index("ix_saved_vehicles_user_id", saved_vehicles.c.user_id)


type AlembicObjectType = Literal[
    "schema",
    "table",
    "column",
    "index",
    "unique_constraint",
    "foreign_key_constraint",
    "check_constraint",
]

type AlembicParentName = Literal[
    "schema_name",
    "table_name",
    "schema_qualified_table_name",
]


def include_routevalue_name(
    name: str | None,
    type_: AlembicObjectType,
    parent_names: MutableMapping[AlembicParentName, str | None],
) -> bool:
    """Limit introspection to RouteValue tables in the public schema."""

    if type_ == "schema":
        return name in (None, "public")

    if type_ == "table":
        return (
            parent_names.get("schema_name") in (None, "public")
            and name is not None
            and f"public.{name}" in metadata.tables
        )

    return True
