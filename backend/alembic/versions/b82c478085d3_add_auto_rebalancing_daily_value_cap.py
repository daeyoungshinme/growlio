"""add auto_rebalancing_daily_value_cap_krw to user_settings

Revision ID: b82c478085d3
Revises: 104aa75dc751
Create Date: 2026-07-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b82c478085d3"
down_revision: str | None = "104aa75dc751"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("auto_rebalancing_daily_value_cap_krw", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "auto_rebalancing_daily_value_cap_krw")
