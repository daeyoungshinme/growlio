"""리밸런싱 알림 상대 이탈 기준(plans/136 A1)

- rebalancing_alerts.relative_threshold_pct: 목표 비중 대비 상대 이탈(%) 기준. null이면 끔(절대 %p 기준만).
  예) 25면 목표 10% 종목이 7.5% 미만·12.5% 초과일 때도 이탈로 본다("5/25 규칙").

배포 순서: 공유 Supabase에 이것을 적용하고 코드를 배포한다(nullable 컬럼 추가라 옛 코드와 호환).

Revision ID: rb1_rebalancing_relative_threshold
Revises: du1_deposit_usd_synced_at
Create Date: 2026-11-19 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "rb1_rebalancing_relative_threshold"
down_revision = "du1_deposit_usd_synced_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rebalancing_alerts", sa.Column("relative_threshold_pct", sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("rebalancing_alerts", "relative_threshold_pct")
