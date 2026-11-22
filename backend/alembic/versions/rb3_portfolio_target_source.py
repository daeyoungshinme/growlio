"""포트폴리오 목표 비중 출처(plans/145 C1)

- portfolios.target_source: MANUAL(직접 입력) | RECOMMENDATION(추천 적용) | TACTICAL(전술 적용). null이면 기록 이전.
- portfolios.target_source_at: 목표 비중을 마지막으로 바꾼 시각(비중만 바꾸면 updated_at이 갱신되지 않아 따로 둔다).

배포 순서: 공유 Supabase에 이것을 적용하고 코드를 배포한다(nullable 컬럼 추가라 옛 코드와 호환).

Revision ID: rb3_portfolio_target_source
Revises: rb2_rebalancing_trade_options
Create Date: 2026-11-22 18:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "rb3_portfolio_target_source"
down_revision = "rb2_rebalancing_trade_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("target_source", sa.String(16), nullable=True))
    op.add_column("portfolios", sa.Column("target_source_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("portfolios", "target_source_at")
    op.drop_column("portfolios", "target_source")
