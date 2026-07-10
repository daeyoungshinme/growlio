"""relax rebalancing_alerts unique constraint to allow per-account rows

Revision ID: as2_relax_rebalancing_alert_unique
Revises: as1_add_portfolio_alert_scope
Create Date: 2026-07-06 00:00:01.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "as2_relax_rebalancing_alert_unique"
down_revision: str | None = "as1_add_portfolio_alert_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_rebalancing_alert_user_portfolio", "rebalancing_alerts", type_="unique")
    op.create_index(
        "uq_rebalancing_alert_aggregate",
        "rebalancing_alerts",
        ["user_id", "portfolio_id"],
        unique=True,
        postgresql_where=sa.text("alert_scope = 'AGGREGATE'"),
    )
    op.create_index(
        "uq_rebalancing_alert_per_account",
        "rebalancing_alerts",
        ["user_id", "portfolio_id", "account_id"],
        unique=True,
        postgresql_where=sa.text("alert_scope = 'PER_ACCOUNT'"),
    )


def downgrade() -> None:
    op.drop_index("uq_rebalancing_alert_per_account", table_name="rebalancing_alerts")
    op.drop_index("uq_rebalancing_alert_aggregate", table_name="rebalancing_alerts")
    op.create_unique_constraint(
        "uq_rebalancing_alert_user_portfolio", "rebalancing_alerts", ["user_id", "portfolio_id"]
    )
