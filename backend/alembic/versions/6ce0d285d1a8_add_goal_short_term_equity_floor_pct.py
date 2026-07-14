"""add goal_short_term_equity_floor_pct

Revision ID: 6ce0d285d1a8
Revises: as9_add_isa_fields
Create Date: 2026-07-13 18:52:16.053804

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "6ce0d285d1a8"
down_revision: str | None = "as9_add_isa_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("goal_short_term_equity_floor_pct", sa.Numeric(precision=5, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "goal_short_term_equity_floor_pct")
