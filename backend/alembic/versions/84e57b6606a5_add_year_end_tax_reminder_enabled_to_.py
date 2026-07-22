"""add year end tax reminder enabled to user settings

Revision ID: 84e57b6606a5
Revises: 51e994cacfd1
Create Date: 2026-07-22 22:22:43.511030

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "84e57b6606a5"
down_revision: str | None = "51e994cacfd1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("year_end_tax_reminder_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "year_end_tax_reminder_enabled")
