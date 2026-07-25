"""add age_group to user_settings

Revision ID: 104aa75dc751
Revises: b1c2d3e4f5a6
Create Date: 2026-07-23 21:10:35.952296

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "104aa75dc751"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("age_group", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("user_settings", "age_group")
