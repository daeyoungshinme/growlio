"""add portfolio_items.group_key/group_label + portfolio_item_members (지수 그룹 리밸런싱, plans/74)

Revision ID: ig1_portfolio_item_groups
Revises: ta5_tactical_use_macro
Create Date: 2026-10-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ig1_portfolio_item_groups"
down_revision: str | None = "ta5_tactical_use_macro"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("portfolio_items", sa.Column("group_key", sa.String(length=64), nullable=True))
    op.add_column("portfolio_items", sa.Column("group_label", sa.String(length=50), nullable=True))
    op.create_table(
        "portfolio_item_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "portfolio_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolio_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="MEMBER"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("portfolio_item_id", "ticker", "market", name="uq_portfolio_item_members_key"),
    )
    op.create_index("idx_portfolio_item_members_item", "portfolio_item_members", ["portfolio_item_id"])


def downgrade() -> None:
    op.drop_index("idx_portfolio_item_members_item", table_name="portfolio_item_members")
    op.drop_table("portfolio_item_members")
    op.drop_column("portfolio_items", "group_label")
    op.drop_column("portfolio_items", "group_key")
