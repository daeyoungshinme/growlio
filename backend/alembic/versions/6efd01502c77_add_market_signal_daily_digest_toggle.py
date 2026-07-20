"""add market signal daily digest toggle

Revision ID: 6efd01502c77
Revises: rm1_remove_auto_dca_settings
Create Date: 2026-07-20 16:23:22.492192

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6efd01502c77"
down_revision: str | None = "rm1_remove_auto_dca_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("market_signal_daily_digest_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "market_signal_daily_digest_enabled")
