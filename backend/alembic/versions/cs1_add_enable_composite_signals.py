"""add enable_composite_signals to rebalancing_alerts

Revision ID: cs1_add_composite_signals
Revises: nt1_add_notify_time
Create Date: 2026-07-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "cs1_add_composite_signals"
down_revision: str | None = "nt1_add_notify_time"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column("enable_composite_signals", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("rebalancing_alerts", "enable_composite_signals")
