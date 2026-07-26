"""add birth_year to user_settings

Revision ID: 4f867b6a40e8
Revises: b82c478085d3
Create Date: 2026-07-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4f867b6a40e8"
down_revision: str | None = "b82c478085d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("birth_year", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "birth_year")
