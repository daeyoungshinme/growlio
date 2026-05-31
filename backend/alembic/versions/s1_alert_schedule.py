"""Add schedule fields to rebalancing_alerts

Revision ID: s1_alert_schedule
Revises: r1_add_rebalancing_alerts
Create Date: 2026-05-31
"""

from alembic import op
import sqlalchemy as sa

revision = "s1_alert_schedule"
down_revision = "r1_add_rebalancing_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column("schedule_type", sa.String(12), nullable=False, server_default="DAILY"),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("schedule_day_of_week", sa.Integer(), nullable=True),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("schedule_day_of_month", sa.Integer(), nullable=True),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("only_when_drift", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("rebalancing_alerts", "only_when_drift")
    op.drop_column("rebalancing_alerts", "schedule_day_of_month")
    op.drop_column("rebalancing_alerts", "schedule_day_of_week")
    op.drop_column("rebalancing_alerts", "schedule_type")
