"""Add optional saved electricity rate and purchasing area; preserve existing data."""

import sqlalchemy as sa
from alembic import op

revision: str = "a19d6e2c740b"
down_revision: str | None = "f2b7c39a106d"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for name, data_type in (
        ("electricity_price_per_kwh", sa.Numeric()),
        ("fuel_market_name", sa.Text()),
        ("fuel_market_latitude", sa.Double()),
        ("fuel_market_longitude", sa.Double()),
    ):
        op.add_column(
            "user_preferences", sa.Column(name, data_type, nullable=True), schema="public"
        )
    op.create_check_constraint(
        "ck_user_preferences_valid_electricity_price",
        "user_preferences",
        "electricity_price_per_kwh IS NULL OR (electricity_price_per_kwh >= 0 "
        "AND electricity_price_per_kwh NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
        schema="public",
    )
    op.create_check_constraint(
        "ck_user_preferences_valid_fuel_market",
        "user_preferences",
        "(fuel_market_name IS NULL AND fuel_market_latitude IS NULL AND fuel_market_longitude IS NULL) "
        "OR (fuel_market_name IS NOT NULL AND fuel_market_latitude IS NOT NULL AND fuel_market_longitude IS NOT NULL "
        "AND length(btrim(fuel_market_name)) BETWEEN 1 AND 200 "
        "AND fuel_market_latitude BETWEEN -90 AND 90 AND fuel_market_longitude BETWEEN -180 AND 180)",
        schema="public",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Saved user preferences must be preserved; use application rollback without schema downgrade"
    )
