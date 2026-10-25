"""add tactical_strategies dip columns (눌림목/웅덩이 현금 투입)

Revision ID: ta3_add_tactical_dip
Revises: ta2_add_tactical_tilt
Create Date: 2026-10-25 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ta3_add_tactical_dip"
down_revision: str | None = "ta2_add_tactical_tilt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tactical_strategies",
        sa.Column("dip_shift_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column("tactical_strategies", sa.Column("dip_level", sa.SmallInteger(), nullable=False, server_default="0"))
    op.add_column(
        "tactical_strategies",
        sa.Column("notified_dip_level", sa.SmallInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("tactical_strategies", "notified_dip_level")
    op.drop_column("tactical_strategies", "dip_level")
    op.drop_column("tactical_strategies", "dip_shift_pct")
