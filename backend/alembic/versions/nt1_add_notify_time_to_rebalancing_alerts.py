"""add notify_time to rebalancing_alerts

Revision ID: nt1_add_notify_time
Revises: cc2fabe2d9eb
Create Date: 2026-06-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "nt1_add_notify_time"
down_revision: str | None = "cc2fabe2d9eb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column("notify_time", sa.String(5), nullable=False, server_default="08:30"),
    )


def downgrade() -> None:
    op.drop_column("rebalancing_alerts", "notify_time")
