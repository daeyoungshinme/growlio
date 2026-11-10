"""환율 알림 출처·계획 환전 금액 — plans/121

- exchange_rate_alerts.source: MANUAL(기본) | FX_PLAN(달러 환전 계획 구간)
- exchange_rate_alerts.planned_usd: 구간 환전 금액(달러) — 발동 메일·푸시에 표시
- exchange_rate_alerts.portfolio_id: 계획 기준 포트폴리오(삭제 시 SET NULL)

배포 순서: 공유 Supabase에 먼저 적용하고 코드를 배포한다(컬럼 추가만이라 옛 코드와 호환).

Revision ID: fx1_exchange_rate_alert_plan_source
Revises: dca1_dca_amount_and_fx_wait
Create Date: 2026-11-10 15:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "fx1_exchange_rate_alert_plan_source"
down_revision = "dca1_dca_amount_and_fx_wait"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exchange_rate_alerts",
        sa.Column("source", sa.String(10), nullable=False, server_default="MANUAL"),
    )
    op.add_column("exchange_rate_alerts", sa.Column("planned_usd", sa.Numeric(18, 2), nullable=True))
    op.add_column(
        "exchange_rate_alerts",
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_exchange_rate_alerts_portfolio_id",
        "exchange_rate_alerts",
        "portfolios",
        ["portfolio_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_exchange_rate_alerts_portfolio", "exchange_rate_alerts", ["portfolio_id"])


def downgrade() -> None:
    op.drop_index("idx_exchange_rate_alerts_portfolio", table_name="exchange_rate_alerts")
    op.drop_constraint("fk_exchange_rate_alerts_portfolio_id", "exchange_rate_alerts", type_="foreignkey")
    op.drop_column("exchange_rate_alerts", "portfolio_id")
    op.drop_column("exchange_rate_alerts", "planned_usd")
    op.drop_column("exchange_rate_alerts", "source")
