"""정기 적립 정액 모드 + 해외 매수 환전 대기 — plans/120

- rebalancing_alerts.dca_amount_krw: 스케줄일 매수 금액(원). NULL이면 기존 목표비중 채우기.
- rebalancing_plan_legs.fx_retry_until / required_usd / available_usd: WAITING_FX(달러 부족 대기) leg 정보.

배포 순서: 공유 Supabase에 먼저 적용하고 코드를 배포한다(컬럼 추가만이라 옛 코드와 호환).

Revision ID: dca1_dca_amount_and_fx_wait
Revises: gd1_goal_start_date_to_date
Create Date: 2026-11-10 10:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "dca1_dca_amount_and_fx_wait"
down_revision = "gd1_goal_start_date_to_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rebalancing_alerts", sa.Column("dca_amount_krw", sa.Numeric(18, 2), nullable=True))
    op.add_column("rebalancing_plan_legs", sa.Column("fx_retry_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rebalancing_plan_legs", sa.Column("required_usd", sa.Numeric(18, 4), nullable=True))
    op.add_column("rebalancing_plan_legs", sa.Column("available_usd", sa.Numeric(18, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("rebalancing_plan_legs", "available_usd")
    op.drop_column("rebalancing_plan_legs", "required_usd")
    op.drop_column("rebalancing_plan_legs", "fx_retry_until")
    op.drop_column("rebalancing_alerts", "dca_amount_krw")
