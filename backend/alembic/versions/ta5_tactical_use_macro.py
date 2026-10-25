"""add tactical_strategies.use_macro, tilt_shift_pct default 0 (매크로 반영 옵션·틸트 기본 끔)

Revision ID: ta5_tactical_use_macro
Revises: ta4_add_tactical_partial
Create Date: 2026-10-25 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ta5_tactical_use_macro"
down_revision: str | None = "ta4_add_tactical_partial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tactical_strategies",
        sa.Column("use_macro", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    # 기존 행의 저장값(10 등)은 그대로 — 새 행의 기본값만 바꾼다
    op.alter_column("tactical_strategies", "tilt_shift_pct", server_default="0")


def downgrade() -> None:
    op.alter_column("tactical_strategies", "tilt_shift_pct", server_default="10")
    op.drop_column("tactical_strategies", "use_macro")
