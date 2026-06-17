"""merge_rebalancing_alert_and_auto

Revision ID: x1_merge_rebalancing_and_auto
Revises: eabe85f7281c
Create Date: 2026-06-01

rebalancing_alerts 테이블에 실행 설정(mode/strategy/account_id/order_type) 추가,
user_settings에서 auto_rebalance_* 컬럼 제거.
기존 활성 자동 리밸런싱 데이터를 rebalancing_alerts로 이전.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "x1_merge_rebalancing_and_auto"
down_revision: str | None = "eabe85f7281c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # rebalancing_alerts 테이블에 4개 컬럼 추가
    op.add_column(
        "rebalancing_alerts",
        sa.Column("mode", sa.String(10), nullable=False, server_default="NOTIFY"),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("strategy", sa.String(20), nullable=False, server_default="BUY_ONLY"),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("asset_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("order_type", sa.String(10), nullable=False, server_default="MARKET"),
    )

    # 기존 auto_rebalance_* 데이터 → rebalancing_alerts 이전
    op.execute(
        """
        INSERT INTO rebalancing_alerts (
            id, user_id, portfolio_id, is_active,
            threshold_pct, schedule_type, only_when_drift,
            mode, strategy, account_id, order_type,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            us.user_id,
            us.auto_rebalance_portfolio_id,
            true,
            us.auto_rebalance_threshold_pct,
            'DAILY',
            true,
            us.auto_rebalance_mode,
            us.auto_rebalance_strategy,
            us.auto_rebalance_account_id,
            us.auto_rebalance_order_type,
            NOW(),
            NOW()
        FROM user_settings us
        WHERE us.auto_rebalance_enabled = TRUE
          AND us.auto_rebalance_portfolio_id IS NOT NULL
        ON CONFLICT (user_id, portfolio_id) DO UPDATE SET
            mode = EXCLUDED.mode,
            strategy = EXCLUDED.strategy,
            account_id = EXCLUDED.account_id,
            order_type = EXCLUDED.order_type,
            is_active = true
        """
    )

    # user_settings에서 auto_rebalance_* 컬럼 9개 삭제
    op.drop_column("user_settings", "auto_rebalance_last_checked_at")
    op.drop_column("user_settings", "auto_rebalance_last_executed_at")
    op.drop_column("user_settings", "auto_rebalance_order_type")
    op.drop_column("user_settings", "auto_rebalance_mode")
    op.drop_column("user_settings", "auto_rebalance_strategy")
    op.drop_column("user_settings", "auto_rebalance_threshold_pct")
    op.drop_column("user_settings", "auto_rebalance_account_id")
    op.drop_column("user_settings", "auto_rebalance_portfolio_id")
    op.drop_column("user_settings", "auto_rebalance_enabled")


def downgrade() -> None:
    # user_settings 컬럼 복원
    op.add_column(
        "user_settings",
        sa.Column("auto_rebalance_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "user_settings", sa.Column("auto_rebalance_portfolio_id", sa.UUID(), nullable=True)
    )
    op.add_column("user_settings", sa.Column("auto_rebalance_account_id", sa.UUID(), nullable=True))
    op.add_column(
        "user_settings",
        sa.Column(
            "auto_rebalance_threshold_pct",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="5.0",
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "auto_rebalance_strategy", sa.String(20), nullable=False, server_default="BUY_ONLY"
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column("auto_rebalance_mode", sa.String(20), nullable=False, server_default="NOTIFY"),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "auto_rebalance_order_type", sa.String(20), nullable=False, server_default="MARKET"
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column("auto_rebalance_last_executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_settings",
        sa.Column("auto_rebalance_last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )

    # rebalancing_alerts 컬럼 제거
    op.drop_column("rebalancing_alerts", "order_type")
    op.drop_column("rebalancing_alerts", "account_id")
    op.drop_column("rebalancing_alerts", "strategy")
    op.drop_column("rebalancing_alerts", "mode")
