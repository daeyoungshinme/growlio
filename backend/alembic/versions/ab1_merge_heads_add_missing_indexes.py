"""merge heads and add missing indexes

Revision ID: ab1_merge_heads_add_missing_indexes
Revises: aa1_drop_securities_table, an1_deposit_trigger_multi_account
Create Date: 2026-06-22

두 브랜치(aa1, an1)를 병합하고 쿼리 패턴에 누락된 인덱스 3개를 추가한다.
- positions(snapshot_id, ticker): composition_calculator IN 쿼리 + ticker 필터링
- rebalancing_alerts(is_active, deposit_trigger_enabled): deposit_monitor 잡 조건
- user_settings(user_id) WHERE auto_dca_enabled=TRUE: dca_auto_buy 잡 조건
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "ab1_merge_heads_add_missing_indexes"
down_revision = ("aa1_drop_securities_table", "an1_deposit_trigger_multi_account")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_positions_snapshot_ticker",
        "positions",
        ["snapshot_id", "ticker"],
        postgresql_where=sa.text("snapshot_id IS NOT NULL"),
    )
    op.create_index(
        "idx_rebalancing_alerts_deposit",
        "rebalancing_alerts",
        ["is_active", "deposit_trigger_enabled"],
    )
    op.create_index(
        "idx_user_settings_auto_dca",
        "user_settings",
        ["user_id"],
        postgresql_where=sa.text("auto_dca_enabled = TRUE"),
    )


def downgrade() -> None:
    op.drop_index("idx_user_settings_auto_dca", table_name="user_settings")
    op.drop_index("idx_rebalancing_alerts_deposit", table_name="rebalancing_alerts")
    op.drop_index("idx_positions_snapshot_ticker", table_name="positions")
