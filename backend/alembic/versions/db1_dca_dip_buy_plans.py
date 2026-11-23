"""낙폭 추매 안내 플랜 — plans/147

- dca_dip_buy_plans: 포트폴리오당 1개. 기준 지수·남은 여윳돈·구간(JSONB)·사이클 기준액·완료 기록

배포 순서: 공유 Supabase에 먼저 적용하고 코드를 배포한다(테이블 추가만이라 옛 코드와 호환).

Revision ID: db1_dca_dip_buy_plans
Revises: rb3_portfolio_target_source
Create Date: 2026-11-23 10:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "db1_dca_dip_buy_plans"
down_revision = "rb3_portfolio_target_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dca_dip_buy_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("index_ticker", sa.String(8), nullable=False, server_default="QQQ"),
        sa.Column("reserve_krw", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tiers", postgresql.JSONB(), nullable=False),
        sa.Column("cycle_base_krw", sa.Numeric(18, 2), nullable=True),
        sa.Column("completed", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("portfolio_id", name="uq_dca_dip_buy_plans_portfolio"),
    )
    op.create_index("idx_dca_dip_buy_plans_user", "dca_dip_buy_plans", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_dca_dip_buy_plans_user", table_name="dca_dip_buy_plans")
    op.drop_table("dca_dip_buy_plans")
