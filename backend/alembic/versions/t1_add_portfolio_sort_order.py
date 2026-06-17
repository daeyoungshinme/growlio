"""Add sort_order to portfolios

Revision ID: t1_add_portfolio_sort_order
Revises: s1_alert_schedule
Create Date: 2026-05-31
"""

import sqlalchemy as sa

from alembic import op

revision = "t1_add_portfolio_sort_order"
down_revision = "s1_alert_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolios",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    # 기존 데이터: user별 created_at 순서로 초기 sort_order 부여
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at) - 1 AS rn
            FROM portfolios
        )
        UPDATE portfolios SET sort_order = ranked.rn FROM ranked WHERE portfolios.id = ranked.id
    """)


def downgrade() -> None:
    op.drop_column("portfolios", "sort_order")
