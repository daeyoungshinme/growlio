"""Add rebalancing_alerts table

Revision ID: r1_add_rebalancing_alerts
Revises: q1_add_performance_indexes
Create Date: 2026-05-31
"""

from alembic import op
import sqlalchemy as sa

revision = "r1_add_rebalancing_alerts"
down_revision = "q1_add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rebalancing_alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("threshold_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "portfolio_id", name="uq_rebalancing_alert_user_portfolio"),
    )
    op.create_index(
        "idx_rebalancing_alerts_user_active",
        "rebalancing_alerts",
        ["user_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("idx_rebalancing_alerts_user_active", table_name="rebalancing_alerts")
    op.drop_table("rebalancing_alerts")
