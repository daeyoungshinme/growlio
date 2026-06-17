"""drop_target_portfolios

target_portfolios 테이블 제거. 데이터는 f9a8b7c6d5e4_add_unified_portfolios 마이그레이션에서
이미 portfolios 테이블로 이관되었음.

Revision ID: k1l2m3n4o5p6
Revises: j1k2l3m4n5o6
Create Date: 2026-05-25

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "k1l2m3n4o5p6"
down_revision: str | None = "j1k2l3m4n5o6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_target_portfolios_user", table_name="target_portfolios")
    op.drop_table("target_portfolios")


def downgrade() -> None:
    op.create_table(
        "target_portfolios",
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
    op.create_index("idx_target_portfolios_user", "target_portfolios", ["user_id"], unique=False)
