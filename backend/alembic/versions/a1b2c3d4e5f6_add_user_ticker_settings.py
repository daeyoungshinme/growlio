"""add_user_ticker_settings

Revision ID: a1b2c3d4e5f6
Revises: b608c0089442
Create Date: 2026-05-11 00:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "b608c0089442"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_ticker_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("dividend_months", postgresql.ARRAY(sa.Integer()), nullable=True),
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
        sa.UniqueConstraint("user_id", "ticker", "market", name="uq_user_ticker_settings"),
    )
    op.create_index("idx_user_ticker_settings_user", "user_ticker_settings", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_user_ticker_settings_user", table_name="user_ticker_settings")
    op.drop_table("user_ticker_settings")
