"""add_snapshots_user_date_index: asset_snapshots(user_id, snapshot_date DESC) 인덱스 추가

Revision ID: aa2_add_snapshots_user_date_index
Revises: z2_positions_normalization
Create Date: 2026-06-15
"""

from alembic import op
from sqlalchemy import text

revision = "aa2_add_snapshots_user_date_index"
down_revision = "z2_positions_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_user_date_desc "
        "ON asset_snapshots (user_id, snapshot_date DESC)"
    ))


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS idx_snapshots_user_date_desc"))
