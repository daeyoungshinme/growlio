"""add_rebalancing_execution_and_auto_rebalance_settings

Revision ID: eabe85f7281c
Revises: w1_add_stock_price_alert
Create Date: 2026-06-01 13:11:07.673045

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "eabe85f7281c"
down_revision: str | None = "w1_add_stock_price_alert"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rebalancing_executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=True),
        sa.Column("triggered_by", sa.String(length=20), nullable=False),
        sa.Column("strategy", sa.String(length=20), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("total_success", sa.Integer(), nullable=False),
        sa.Column("total_fail", sa.Integer(), nullable=False),
        sa.Column("total_skipped", sa.Integer(), nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_rebalancing_executions_user",
        "rebalancing_executions",
        ["user_id", "executed_at"],
        unique=False,
    )

    op.add_column(
        "user_settings",
        sa.Column("auto_rebalance_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "user_settings", sa.Column("auto_rebalance_portfolio_id", sa.UUID(), nullable=True)
    )
    op.add_column("user_settings", sa.Column("auto_rebalance_account_id", sa.UUID(), nullable=True))
    op.add_column(
        "user_settings",
        sa.Column(
            "auto_rebalance_threshold_pct",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="5.0",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "auto_rebalance_strategy",
            sa.String(length=20),
            nullable=False,
            server_default="BUY_ONLY",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "auto_rebalance_mode", sa.String(length=20), nullable=False, server_default="NOTIFY"
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "auto_rebalance_order_type",
            sa.String(length=20),
            nullable=False,
            server_default="MARKET",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column("auto_rebalance_last_executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_settings",
        sa.Column("auto_rebalance_last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "auto_rebalance_last_checked_at")
    op.drop_column("user_settings", "auto_rebalance_last_executed_at")
    op.drop_column("user_settings", "auto_rebalance_order_type")
    op.drop_column("user_settings", "auto_rebalance_mode")
    op.drop_column("user_settings", "auto_rebalance_strategy")
    op.drop_column("user_settings", "auto_rebalance_threshold_pct")
    op.drop_column("user_settings", "auto_rebalance_account_id")
    op.drop_column("user_settings", "auto_rebalance_portfolio_id")
    op.drop_column("user_settings", "auto_rebalance_enabled")
    op.drop_index("idx_rebalancing_executions_user", table_name="rebalancing_executions")
    op.drop_table("rebalancing_executions")
