"""Add optional vehicle mass and provenance to saved vehicles.

Revision ID: c8e4b72a91d3
Revises: 7b3c2a91d0ef
"""

import sqlalchemy as sa
from alembic import op

revision: str = "c8e4b72a91d3"
down_revision: str | None = "7b3c2a91d0ef"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "saved_vehicles",
        sa.Column("vehicle_mass_kg", sa.Numeric(), nullable=True),
        schema="public",
    )

    op.add_column(
        "saved_vehicles",
        sa.Column(
            "vehicle_mass_source",
            sa.String(length=64),
            nullable=True,
        ),
        schema="public",
    )

    op.add_column(
        "saved_vehicles",
        sa.Column(
            "vehicle_mass_reference",
            sa.Text(),
            nullable=True,
        ),
        schema="public",
    )

    op.create_check_constraint(
        "ck_saved_vehicles_positive_mass",
        "saved_vehicles",
        "vehicle_mass_kg IS NULL OR vehicle_mass_kg > 0",
        schema="public",
    )

    op.create_check_constraint(
        "ck_saved_vehicles_mass_presence",
        "saved_vehicles",
        "(vehicle_mass_kg IS NULL AND vehicle_mass_source IS NULL "
        "AND vehicle_mass_reference IS NULL) "
        "OR (vehicle_mass_kg IS NOT NULL "
        "AND vehicle_mass_source IS NOT NULL)",
        schema="public",
    )

    op.create_check_constraint(
        "ck_saved_vehicles_mass_source",
        "saved_vehicles",
        "vehicle_mass_source IS NULL OR vehicle_mass_source IN "
        "('manufacturer_curb_weight', 'epa_test_weight', "
        "'user_provided')",
        schema="public",
    )

    op.create_check_constraint(
        "ck_saved_vehicles_mass_reference",
        "saved_vehicles",
        "vehicle_mass_reference IS NULL OR length(btrim(vehicle_mass_reference)) > 0",
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_saved_vehicles_mass_reference",
        "saved_vehicles",
        schema="public",
        type_="check",
    )

    op.drop_constraint(
        "ck_saved_vehicles_mass_source",
        "saved_vehicles",
        schema="public",
        type_="check",
    )

    op.drop_constraint(
        "ck_saved_vehicles_mass_presence",
        "saved_vehicles",
        schema="public",
        type_="check",
    )

    op.drop_constraint(
        "ck_saved_vehicles_positive_mass",
        "saved_vehicles",
        schema="public",
        type_="check",
    )

    op.drop_column(
        "saved_vehicles",
        "vehicle_mass_reference",
        schema="public",
    )

    op.drop_column(
        "saved_vehicles",
        "vehicle_mass_source",
        schema="public",
    )

    op.drop_column(
        "saved_vehicles",
        "vehicle_mass_kg",
        schema="public",
    )
