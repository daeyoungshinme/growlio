"""add tactical_strategies tilt columns (나스닥/S&P 틸트: 실질금리+상대강도, 월 1회 갱신)

Revision ID: ta2_add_tactical_tilt
Revises: ta1_add_tactical_strategies
Create Date: 2026-10-21 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ta2_add_tactical_tilt"
down_revision: str | None = "ta1_add_tactical_strategies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tactical_strategies",
        sa.Column("tilt_shift_pct", sa.Numeric(5, 2), nullable=False, server_default="10"),
    )
    op.add_column("tactical_strategies", sa.Column("last_tilt", sa.String(12), nullable=True))
    op.add_column("tactical_strategies", sa.Column("tilt_evaluated_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("tactical_strategies", "tilt_evaluated_on")
    op.drop_column("tactical_strategies", "last_tilt")
    op.drop_column("tactical_strategies", "tilt_shift_pct")
