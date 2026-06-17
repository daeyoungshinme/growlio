"""add_unified_portfolios

Revision ID: f9a8b7c6d5e4
Revises: e8a93587d968
Create Date: 2026-05-19 10:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f9a8b7c6d5e4"
down_revision: str | None = "33a12f46ad9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("base_type", sa.String(length=20), nullable=False, server_default="STOCK_ONLY"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_portfolios_user", "portfolios", ["user_id"], unique=False)

    # backtest_portfolios 데이터 이관
    # holdings: [{ticker, market, weight}] → items: [{ticker, name, market, weight}]
    op.execute("""
        INSERT INTO portfolios (id, user_id, name, items, base_type, created_at, updated_at)
        SELECT
            id,
            user_id,
            name,
            COALESCE(
                (
                    SELECT jsonb_agg(
                        jsonb_build_object(
                            'ticker', h->>'ticker',
                            'name',   COALESCE(h->>'name', ''),
                            'market', h->>'market',
                            'weight', (h->>'weight')::float
                        )
                    )
                    FROM jsonb_array_elements(holdings) AS h
                ),
                '[]'::jsonb
            ),
            'STOCK_ONLY',
            created_at,
            updated_at
        FROM backtest_portfolios
        ON CONFLICT (id) DO NOTHING
    """)

    # target_portfolios 데이터 이관 (포맷 동일)
    op.execute("""
        INSERT INTO portfolios (id, user_id, name, items, base_type, created_at, updated_at)
        SELECT id, user_id, name, items, base_type, created_at, updated_at
        FROM target_portfolios
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("idx_portfolios_user", table_name="portfolios")
    op.drop_table("portfolios")
