"""add tactical_strategies partial apply columns (분할 적용 진행 상태)

Revision ID: ta4_add_tactical_partial
Revises: ta3_add_tactical_dip
Create Date: 2026-10-25 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ta4_add_tactical_partial"
down_revision: str | None = "ta3_add_tactical_dip"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tactical_strategies", sa.Column("partial_regime", sa.String(12), nullable=True))
    op.add_column("tactical_strategies", sa.Column("partial_applied_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("tactical_strategies", "partial_applied_on")
    op.drop_column("tactical_strategies", "partial_regime")
