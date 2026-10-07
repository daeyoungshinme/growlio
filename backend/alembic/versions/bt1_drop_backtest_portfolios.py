"""drop legacy backtest_portfolios table

`f9a8b7c6d5e4_add_unified_portfolios`(2026-05)에서 데이터를 통합 `portfolios`로 이관한 뒤
남아 있던 레거시 테이블. 이를 쓰던 `/backtest/portfolios` CRUD는 UI 호출처가 없어 제거했다
(2026-10-07 기준 운영 행 0건 확인).

Revision ID: bt1_drop_backtest_portfolios
Revises: tx1_add_income_bracket
Create Date: 2026-10-07 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "bt1_drop_backtest_portfolios"
down_revision = "tx1_add_income_bracket"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_backtest_portfolios_user", table_name="backtest_portfolios")
    op.drop_table("backtest_portfolios")


def downgrade() -> None:
    op.create_table(
        "backtest_portfolios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("holdings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_backtest_portfolios_user", "backtest_portfolios", ["user_id"], unique=False)
