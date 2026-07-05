"""move composite signal alert toggle from per-portfolio to user-level

Revision ID: cs2_composite_signal_user_level
Revises: cs1_add_composite_signals
Create Date: 2026-07-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "cs2_composite_signal_user_level"
down_revision: str | None = "cs1_add_composite_signals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("composite_signal_alerts_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )

    # 기존 포트폴리오별 설정을 최대한 보존: 그 유저의 알림 중 하나라도 활성화되어 있었다면 유지(true),
    # 알림이 존재하는데 전부 비활성화였다면 유저 단위도 false로 이관. 알림이 아예 없던 유저는 기본값(true) 유지.
    op.execute(
        """
        UPDATE user_settings us
        SET composite_signal_alerts_enabled = FALSE
        WHERE EXISTS (SELECT 1 FROM rebalancing_alerts ra WHERE ra.user_id = us.user_id)
          AND NOT EXISTS (
              SELECT 1 FROM rebalancing_alerts ra
              WHERE ra.user_id = us.user_id AND ra.enable_composite_signals = TRUE
          )
        """
    )

    op.drop_column("rebalancing_alerts", "enable_composite_signals")


def downgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column("enable_composite_signals", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.drop_column("user_settings", "composite_signal_alerts_enabled")
