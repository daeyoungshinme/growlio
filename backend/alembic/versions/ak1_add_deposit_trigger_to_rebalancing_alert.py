"""add deposit trigger fields to rebalancing_alerts

Revision ID: ak1_add_deposit_trigger_to_rebalancing_alert
Revises: aj1_drop_duplicate_asset_account_indexes
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "ak1_add_deposit_trigger_to_rebalancing_alert"
down_revision = "aj1_drop_duplicate_asset_account_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column("deposit_trigger_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("deposit_trigger_account_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("deposit_trigger_min_amount_krw", sa.Integer(), nullable=True),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("last_known_deposit_krw", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("last_deposit_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_rebalancing_alert_deposit_account",
        "rebalancing_alerts",
        "asset_accounts",
        ["deposit_trigger_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_rebalancing_alerts_deposit_trigger",
        "rebalancing_alerts",
        ["deposit_trigger_enabled", "is_active"],
        postgresql_where=sa.text("deposit_trigger_enabled = true"),
    )


def downgrade() -> None:
    op.drop_index("idx_rebalancing_alerts_deposit_trigger", table_name="rebalancing_alerts")
    op.drop_constraint(
        "fk_rebalancing_alert_deposit_account",
        "rebalancing_alerts",
        type_="foreignkey",
    )
    op.drop_column("rebalancing_alerts", "last_deposit_checked_at")
    op.drop_column("rebalancing_alerts", "last_known_deposit_krw")
    op.drop_column("rebalancing_alerts", "deposit_trigger_min_amount_krw")
    op.drop_column("rebalancing_alerts", "deposit_trigger_account_id")
    op.drop_column("rebalancing_alerts", "deposit_trigger_enabled")
