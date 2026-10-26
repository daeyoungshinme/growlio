"""add portfolio_item_members.leverage (레버리지 ETF 노출 기준 그룹 합산, plans/74 후속)

Revision ID: ig2_portfolio_item_member_leverage
Revises: ig1_portfolio_item_groups
Create Date: 2026-10-26 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ig2_portfolio_item_member_leverage"
down_revision: str | None = "ig1_portfolio_item_groups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portfolio_item_members",
        sa.Column("leverage", sa.Numeric(4, 2), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("portfolio_item_members", "leverage")
