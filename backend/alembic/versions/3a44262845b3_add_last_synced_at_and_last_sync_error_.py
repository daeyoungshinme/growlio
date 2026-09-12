"""add last_synced_at and last_sync_error to asset_accounts

Revision ID: 3a44262845b3
Revises: c1a2b3d4e5f6
Create Date: 2026-09-13 00:20:57.143620

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3a44262845b3"
down_revision: str | None = "c1a2b3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("asset_accounts", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("asset_accounts", sa.Column("last_sync_error", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("asset_accounts", "last_sync_error")
    op.drop_column("asset_accounts", "last_synced_at")
