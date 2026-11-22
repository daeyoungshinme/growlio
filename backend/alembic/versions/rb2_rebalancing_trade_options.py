"""리밸런싱 알림 거래 방식 옵션(plans/145 PR3)

- rebalancing_alerts.dca_allocation_mode: 정액 적립 분할 방식. TARGET(목표 비중대로, 기존 동작) | GAP_FIRST(목표에
  모자란 종목부터 부족액 비례로 먼저 채우고 남는 금액은 목표 비중대로).
- rebalancing_alerts.trade_to_band: 켜면 이탈 항목을 목표가 아니라 이탈 기준선(허용 범위 경계)까지만 되돌린다.
- rebalancing_alerts.min_trade_krw: 이보다 작은 주문은 플랜에 담지 않는다. null이면 제한 없음.

배포 순서: 공유 Supabase에 이것을 적용하고 코드를 배포한다(기본값이 있는 컬럼 추가라 옛 코드와 호환).

Revision ID: rb2_rebalancing_trade_options
Revises: rb1_rebalancing_relative_threshold
Create Date: 2026-11-22 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "rb2_rebalancing_trade_options"
down_revision = "rb1_rebalancing_relative_threshold"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column("dca_allocation_mode", sa.String(16), nullable=False, server_default="TARGET"),
    )
    op.add_column(
        "rebalancing_alerts",
        sa.Column("trade_to_band", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("rebalancing_alerts", sa.Column("min_trade_krw", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("rebalancing_alerts", "min_trade_krw")
    op.drop_column("rebalancing_alerts", "trade_to_band")
    op.drop_column("rebalancing_alerts", "dca_allocation_mode")
