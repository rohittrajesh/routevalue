"""Add shared elevation quota accounting; preserve all existing business data."""

import sqlalchemy as sa
from alembic import op

revision: str = "f2b7c39a106d"
down_revision: str | None = "e8a1d4c209bf"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "elevation_call_reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        schema="public",
    )
    op.create_index(
        "ix_elevation_calls_reserved_at",
        "elevation_call_reservations",
        ["reserved_at"],
        schema="public",
    )


def downgrade() -> None:
    # Deliberately require an explicit operator decision to reset durable quotas.
    # Dropping accounting during a rollback could permit excess upstream calls.
    raise RuntimeError(
        "Quota history must be preserved; use application rollback without schema downgrade"
    )
