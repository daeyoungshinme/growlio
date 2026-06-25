"""remove deposit trigger feature

Revision ID: ac1_remove_deposit_trigger
Revises: ab1_merge_heads_add_missing_indexes
Create Date: 2026-06-24

예수금 입금 감지 기능 전체 제거:
- rebalancing_alert_deposit_accounts 테이블 삭제
- rebalancing_alerts 테이블에서 deposit_trigger_enabled, deposit_trigger_min_amount_krw,
  last_deposit_checked_at 컬럼 삭제
- ab1에서 추가된 idx_rebalancing_alerts_deposit 인덱스 삭제
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "ac1_remove_deposit_trigger"
down_revision = "ab1_merge_heads_add_missing_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_rebalancing_alerts_deposit", table_name="rebalancing_alerts")
    op.drop_table("rebalancing_alert_deposit_accounts")
    op.drop_column("rebalancing_alerts", "deposit_trigger_enabled")
    op.drop_column("rebalancing_alerts", "deposit_trigger_min_amount_krw")
    op.drop_column("rebalancing_alerts", "last_deposit_checked_at")


def downgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column("last_deposit_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("deposit_trigger_min_amount_krw", sa.Integer(), nullable=True),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("deposit_trigger_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_table(
        "rebalancing_alert_deposit_accounts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_known_deposit_krw", sa.Numeric(18, 2), nullable=True),
        sa.ForeignKeyConstraint(["alert_id"], ["rebalancing_alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["asset_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alert_id", "account_id", name="uq_alert_deposit_account"),
    )
    op.create_index(
        "idx_alert_deposit_accounts_alert",
        "rebalancing_alert_deposit_accounts",
        ["alert_id"],
    )
    op.create_index(
        "idx_rebalancing_alerts_deposit",
        "rebalancing_alerts",
        ["is_active", "deposit_trigger_enabled"],
    )
