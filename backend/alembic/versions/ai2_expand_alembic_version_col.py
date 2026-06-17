"""expand alembic_version.version_num to VARCHAR(255)

Revision ID: ai2_expand_alembic_version_col
Revises: ai1_add_market_condition_mode
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op

revision = "ai2_expand_alembic_version_col"
down_revision = "ai1_add_market_condition_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")


def downgrade() -> None:
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)")
