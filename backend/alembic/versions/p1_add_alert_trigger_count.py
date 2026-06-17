"""Add max_trigger_count and trigger_count to exchange_rate_alerts

Revision ID: p1_add_alert_trigger_count
Revises: o1_security_improvements
Create Date: 2026-05-29
"""

import sqlalchemy as sa

from alembic import op

revision = "p1_add_alert_trigger_count"
down_revision = "o1_security_improvements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exchange_rate_alerts",
        sa.Column("max_trigger_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "exchange_rate_alerts",
        sa.Column("trigger_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("exchange_rate_alerts", "trigger_count")
    op.drop_column("exchange_rate_alerts", "max_trigger_count")
