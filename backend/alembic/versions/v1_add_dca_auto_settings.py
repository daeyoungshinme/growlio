"""Add auto DCA settings to user_settings

Revision ID: v1_add_dca_auto_settings
Revises: u1_add_snapshot_account_index
Create Date: 2026-05-31
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "v1_add_dca_auto_settings"
down_revision = "u1_add_snapshot_account_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("auto_dca_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("user_settings", sa.Column("auto_dca_day", sa.Integer(), nullable=True))
    op.add_column("user_settings", sa.Column("auto_dca_amount", sa.Numeric(18, 2), nullable=True))
    op.add_column(
        "user_settings",
        sa.Column("auto_dca_portfolio_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "user_settings",
        sa.Column("auto_dca_account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "user_settings",
        sa.Column("auto_dca_last_executed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "auto_dca_last_executed_at")
    op.drop_column("user_settings", "auto_dca_account_id")
    op.drop_column("user_settings", "auto_dca_portfolio_id")
    op.drop_column("user_settings", "auto_dca_amount")
    op.drop_column("user_settings", "auto_dca_day")
    op.drop_column("user_settings", "auto_dca_enabled")
