"""추가 환전 항목(여행 등) — plans/123

- fx_extra_needs: 이름·금액(USD)·이미 환전한 금액·필요일
- exchange_rate_alerts.fx_need_id: 항목 구간 알림(항목 삭제 시 CASCADE)

배포 순서: 공유 Supabase에 먼저 적용하고 코드를 배포한다(테이블·컬럼 추가만이라 옛 코드와 호환).

Revision ID: fx2_fx_extra_needs
Revises: fx1_exchange_rate_alert_plan_source
Create Date: 2026-11-11 10:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "fx2_fx_extra_needs"
down_revision = "fx1_exchange_rate_alert_plan_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fx_extra_needs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("amount_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("exchanged_usd", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_fx_extra_needs_user", "fx_extra_needs", ["user_id"])
    op.add_column(
        "exchange_rate_alerts",
        sa.Column("fx_need_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_exchange_rate_alerts_fx_need_id",
        "exchange_rate_alerts",
        "fx_extra_needs",
        ["fx_need_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_exchange_rate_alerts_fx_need", "exchange_rate_alerts", ["fx_need_id"])


def downgrade() -> None:
    op.drop_index("idx_exchange_rate_alerts_fx_need", table_name="exchange_rate_alerts")
    op.drop_constraint("fk_exchange_rate_alerts_fx_need_id", "exchange_rate_alerts", type_="foreignkey")
    op.drop_column("exchange_rate_alerts", "fx_need_id")
    op.drop_index("idx_fx_extra_needs_user", table_name="fx_extra_needs")
    op.drop_table("fx_extra_needs")
