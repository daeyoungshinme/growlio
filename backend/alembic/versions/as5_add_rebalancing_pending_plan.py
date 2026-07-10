"""add rebalancing pending plan tables + buy_wait_minutes

Revision ID: as5_add_rebalancing_pending_plan
Revises: as4_repair_alert_scope_drift
Create Date: 2026-07-08 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "as5_add_rebalancing_pending_plan"
down_revision: str | None = "as4_repair_alert_scope_drift"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column("buy_wait_minutes", sa.Integer(), nullable=False, server_default="10"),
    )

    op.create_table(
        "rebalancing_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "alert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rebalancing_alerts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("strategy", sa.String(20), nullable=False),
        sa.Column("order_type", sa.String(10), nullable=False),
        sa.Column("composite_level_at_plan", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_rebalancing_plans_user_created", "rebalancing_plans", ["user_id", "created_at"])
    op.create_index("idx_rebalancing_plans_alert", "rebalancing_plans", ["alert_id"])

    op.create_table(
        "rebalancing_plan_legs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rebalancing_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(20), nullable=True),
        sa.Column("action_token_hash", sa.String(64), nullable=True),
        sa.Column("token_consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rebalancing_executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_rebalancing_plan_legs_plan", "rebalancing_plan_legs", ["plan_id"])
    op.create_index("idx_rebalancing_plan_legs_status_deadline", "rebalancing_plan_legs", ["status", "deadline_at"])
    op.create_index(
        "uq_rebalancing_plan_legs_token_hash",
        "rebalancing_plan_legs",
        ["action_token_hash"],
        unique=True,
        postgresql_where=sa.text("action_token_hash IS NOT NULL"),
    )

    op.create_table(
        "rebalancing_plan_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "leg_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rebalancing_plan_legs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("market", sa.String(20), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(50), nullable=True),
        sa.Column("order_type", sa.String(10), nullable=False, server_default="MARKET"),
        sa.Column("limit_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("reference_price", sa.Numeric(18, 2), nullable=True),
    )
    op.create_index("idx_rebalancing_plan_items_leg", "rebalancing_plan_items", ["leg_id"])


def downgrade() -> None:
    op.drop_index("idx_rebalancing_plan_items_leg", table_name="rebalancing_plan_items")
    op.drop_table("rebalancing_plan_items")

    op.drop_index("uq_rebalancing_plan_legs_token_hash", table_name="rebalancing_plan_legs")
    op.drop_index("idx_rebalancing_plan_legs_status_deadline", table_name="rebalancing_plan_legs")
    op.drop_index("idx_rebalancing_plan_legs_plan", table_name="rebalancing_plan_legs")
    op.drop_table("rebalancing_plan_legs")

    op.drop_index("idx_rebalancing_plans_alert", table_name="rebalancing_plans")
    op.drop_index("idx_rebalancing_plans_user_created", table_name="rebalancing_plans")
    op.drop_table("rebalancing_plans")

    op.drop_column("rebalancing_alerts", "buy_wait_minutes")
