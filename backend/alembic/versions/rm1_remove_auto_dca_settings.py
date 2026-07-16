"""Remove auto DCA settings from user_settings (feature removed)

Revision ID: rm1_remove_auto_dca_settings
Revises: 717e507af8ab
Create Date: 2026-07-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "rm1_remove_auto_dca_settings"
down_revision = "717e507af8ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_user_settings_auto_dca", table_name="user_settings")
    op.drop_column("user_settings", "auto_dca_last_executed_at")
    op.drop_column("user_settings", "auto_dca_account_id")
    op.drop_column("user_settings", "auto_dca_portfolio_id")
    op.drop_column("user_settings", "auto_dca_amount")
    op.drop_column("user_settings", "auto_dca_day")
    op.drop_column("user_settings", "auto_dca_enabled")


def downgrade() -> None:
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
    op.create_index(
        "idx_user_settings_auto_dca",
        "user_settings",
        ["user_id"],
        postgresql_where=sa.text("auto_dca_enabled = TRUE"),
    )
