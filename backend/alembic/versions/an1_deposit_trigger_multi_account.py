"""예수금 입금 감지 — 단일 계좌 FK를 다중 계좌 association 테이블로 교체

Revision ID: an1_deposit_trigger_multi_account
Revises: am1_add_trigger_condition_to_rebalancing_alert
Create Date: 2026-06-21

"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "an1_deposit_trigger_multi_account"
down_revision = "am1_add_trigger_condition_to_rebalancing_alert"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 새 association 테이블 생성
    op.create_table(
        "rebalancing_alert_deposit_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "alert_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rebalancing_alerts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("asset_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("last_known_deposit_krw", sa.Numeric(18, 2), nullable=True),
    )
    op.create_unique_constraint(
        "uq_alert_deposit_account",
        "rebalancing_alert_deposit_accounts",
        ["alert_id", "account_id"],
    )
    op.create_index(
        "idx_alert_deposit_accounts_alert",
        "rebalancing_alert_deposit_accounts",
        ["alert_id"],
    )

    # 2) 기존 단일 계좌 데이터 마이그레이션
    op.execute(
        """
        INSERT INTO rebalancing_alert_deposit_accounts
            (id, alert_id, account_id, last_known_deposit_krw)
        SELECT
            gen_random_uuid(),
            id,
            deposit_trigger_account_id,
            last_known_deposit_krw
        FROM rebalancing_alerts
        WHERE deposit_trigger_account_id IS NOT NULL
        """
    )

    # 3) 구 컬럼 제거
    op.drop_column("rebalancing_alerts", "deposit_trigger_account_id")
    op.drop_column("rebalancing_alerts", "last_known_deposit_krw")


def downgrade() -> None:
    # 단일 계좌 컬럼 복원 (대표값: alert당 첫 번째 account만)
    op.add_column(
        "rebalancing_alerts",
        sa.Column(
            "deposit_trigger_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("asset_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("last_known_deposit_krw", sa.Numeric(18, 2), nullable=True),
    )
    op.execute(
        """
        UPDATE rebalancing_alerts ra
        SET
            deposit_trigger_account_id = da.account_id,
            last_known_deposit_krw = da.last_known_deposit_krw
        FROM (
            SELECT DISTINCT ON (alert_id)
                alert_id, account_id, last_known_deposit_krw
            FROM rebalancing_alert_deposit_accounts
            ORDER BY alert_id
        ) da
        WHERE ra.id = da.alert_id
        """
    )
    op.drop_index("idx_alert_deposit_accounts_alert", "rebalancing_alert_deposit_accounts")
    op.drop_constraint("uq_alert_deposit_account", "rebalancing_alert_deposit_accounts")
    op.drop_table("rebalancing_alert_deposit_accounts")
