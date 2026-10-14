"""Create durable EIA gasoline pricing snapshot tables.

Revision ID: e8a1d4c209bf
Revises: c8e4b72a91d3

The migration adds global pricing cache storage.
It does not modify existing user or vehicle data.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "e8a1d4c209bf"
down_revision: str | None = "c8e4b72a91d3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create region snapshots and grade-specific observations."""

    op.create_table(
        "eia_pricing_snapshots",
        sa.Column(
            "region_id",
            sa.String(length=64),
            primary_key=True,
        ),
        sa.Column(
            "geographic_scope",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "display_name",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "workbook_url",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(region_id)) > 0",
            name="ck_eia_snapshots_region_nonblank",
        ),
        sa.CheckConstraint(
            "length(btrim(display_name)) > 0",
            name="ck_eia_snapshots_name_nonblank",
        ),
        sa.CheckConstraint(
            "provider = 'EIA'",
            name="ck_eia_snapshots_provider",
        ),
        sa.CheckConstraint(
            "geographic_scope IN ('national', 'region', 'state', 'metro')",
            name="ck_eia_snapshots_scope",
        ),
        sa.CheckConstraint(
            "length(btrim(workbook_url)) > 0",
            name="ck_eia_snapshots_url_nonblank",
        ),
        schema="public",
    )

    op.create_table(
        "eia_pricing_observations",
        sa.Column(
            "region_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "fuel_grade",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "series_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "price_per_gallon",
            sa.Numeric(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "region_id",
            "fuel_grade",
            name="pk_eia_pricing_observations",
        ),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["public.eia_pricing_snapshots.region_id"],
            ondelete="CASCADE",
            name="fk_eia_observations_snapshot",
        ),
        sa.UniqueConstraint(
            "region_id",
            "series_id",
            name="uq_eia_observations_region_series",
        ),
        sa.CheckConstraint(
            "fuel_grade IN ('regular', 'midgrade', 'premium')",
            name="ck_eia_observations_grade",
        ),
        sa.CheckConstraint(
            "length(btrim(series_id)) > 0",
            name="ck_eia_observations_series_nonblank",
        ),
        sa.CheckConstraint(
            "price_per_gallon >= 0 AND price_per_gallon != 'NaN'::numeric",
            name="ck_eia_observations_nonnegative_price",
        ),
        schema="public",
    )


def downgrade() -> None:
    """Remove only the EIA pricing cache tables."""

    op.drop_table(
        "eia_pricing_observations",
        schema="public",
    )

    op.drop_table(
        "eia_pricing_snapshots",
        schema="public",
    )
