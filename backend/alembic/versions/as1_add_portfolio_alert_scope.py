"""add alert_scope to portfolios

Revision ID: as1_add_portfolio_alert_scope
Revises: ob1_remove_open_banking
Create Date: 2026-07-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "as1_add_portfolio_alert_scope"
down_revision: str | None = "ob1_remove_open_banking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portfolios",
        sa.Column("alert_scope", sa.String(20), nullable=False, server_default="AGGREGATE"),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("alert_scope", sa.String(20), nullable=False, server_default="AGGREGATE"),
    )


def downgrade() -> None:
    op.drop_column("rebalancing_alerts", "alert_scope")
    op.drop_column("portfolios", "alert_scope")
