"""Add monthly_report_enabled column to user_settings

Revision ID: ae1_add_monthly_report_enabled
Revises: ad1_add_stock_alert_ticker_index
Create Date: 2026-06-09
"""

import sqlalchemy as sa
from alembic import op

revision = "ae1_add_monthly_report_enabled"
down_revision = "ad1_add_stock_alert_ticker_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column(
            "monthly_report_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "monthly_report_enabled")
