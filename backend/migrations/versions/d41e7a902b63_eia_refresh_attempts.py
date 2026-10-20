"""Add bounded shared retry state for hosted EIA operations; preserve business data."""

import sqlalchemy as sa
from alembic import op

revision: str = "d41e7a902b63"
down_revision: str | None = "a19d6e2c740b"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "eia_refresh_attempts",
        sa.Column("region_id", sa.String(3), primary_key=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("region_id IN ('SCA', 'NUS')", name="ck_eia_refresh_attempt_region"),
        schema="public",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Preserve refresh retry history; roll back application code without dropping state"
    )
