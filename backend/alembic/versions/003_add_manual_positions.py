"""add_manual_positions

Revision ID: 003
Revises: 002
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("asset_accounts", sa.Column("manual_positions", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("asset_accounts", "manual_positions")
