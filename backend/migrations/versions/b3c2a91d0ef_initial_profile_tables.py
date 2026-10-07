"""Create RouteValue user, identity, preference, and vehicle tables.

Revision ID: 7b3c2a91d0ef
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision: str = "7b3c2a91d0ef"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="public",
    )

    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["public.users.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "issuer",
            "subject",
            name="uq_auth_identities_issuer_subject",
        ),
        sa.CheckConstraint(
            "length(btrim(issuer)) > 0 AND length(btrim(subject)) > 0",
            name="ck_auth_identities_nonblank_subject",
        ),
        schema="public",
    )

    op.create_table(
        "saved_vehicles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("make", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("configuration", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column(
            "specification_retrieved_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("powertrain", sa.String(16), nullable=False),
        sa.Column("gasoline_grade", sa.String(16), nullable=True),
        sa.Column("combined_mpg", sa.Numeric(), nullable=True),
        sa.Column("city_mpg", sa.Numeric(), nullable=True),
        sa.Column("highway_mpg", sa.Numeric(), nullable=True),
        sa.Column("combined_kwh_per_mile", sa.Numeric(), nullable=True),
        sa.Column("city_kwh_per_mile", sa.Numeric(), nullable=True),
        sa.Column("highway_kwh_per_mile", sa.Numeric(), nullable=True),
        sa.Column(
            "saved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["public.users.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "id",
            "user_id",
            name="uq_saved_vehicles_id_owner",
        ),
        sa.CheckConstraint(
            "year > 0",
            name="ck_saved_vehicles_valid_year",
        ),
        sa.CheckConstraint(
            "length(btrim(make)) > 0 AND length(btrim(model)) > 0 "
            "AND length(btrim(configuration)) > 0 AND length(btrim(source)) > 0 "
            "AND length(btrim(source_id)) > 0",
            name="ck_saved_vehicles_nonblank_identity",
        ),
        sa.CheckConstraint(
            "gasoline_grade IS NULL OR gasoline_grade IN ('regular', 'midgrade', 'premium')",
            name="ck_saved_vehicles_gasoline_grade",
        ),
        sa.CheckConstraint(
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
            sa.CheckConstraint(
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
        schema="public",
    )

    op.create_index(
        "ix_auth_identities_user_id",
        "auth_identities",
        ["user_id"],
        schema="public",
    )

    op.create_index(
        "ix_saved_vehicles_user_id",
        "saved_vehicles",
        ["user_id"],
        schema="public",
    )

    op.create_table(
        "user_preferences",
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("value_of_time_per_hour", sa.Numeric(), nullable=True),
        sa.Column("default_vehicle_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["public.users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["default_vehicle_id", "user_id"],
            ["public.saved_vehicles.id", "public.saved_vehicles.user_id"],
            name="fk_preferences_default_owned_vehicle",
        ),
        sa.CheckConstraint(
            "value_of_time_per_hour IS NULL OR value_of_time_per_hour >= 0",
            name="ck_user_preferences_nonnegative_value_of_time",
        ),
        schema="public",
    )


def downgrade() -> None:
    op.drop_table("user_preferences", schema="public")

    op.drop_index(
        "ix_saved_vehicles_user_id",
        table_name="saved_vehicles",
        schema="public",
    )

    op.drop_index(
        "ix_auth_identities_user_id",
        table_name="auth_identities",
        schema="public",
    )

    op.drop_table("saved_vehicles", schema="public")
    op.drop_table("auth_identities", schema="public")
    op.drop_table("users", schema="public")
