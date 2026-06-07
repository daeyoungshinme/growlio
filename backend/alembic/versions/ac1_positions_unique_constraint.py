"""Add unique constraint on positions (account_id, ticker) for current positions

Revision ID: ac1_positions_unique_constraint
Revises: 072c1f0d9e47
Create Date: 2026-06-07
"""

from alembic import op

revision = "ac1_positions_unique_constraint"
down_revision = "072c1f0d9e47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # snapshot_id IS NULL인 현재 포지션에서 (account_id, ticker) 중복 방지
    # 기존 중복 데이터가 있을 경우 마이그레이션 실패 → 수동 정리 필요
    op.create_index(
        "uq_positions_account_ticker_current",
        "positions",
        ["account_id", "ticker"],
        unique=True,
        postgresql_where="snapshot_id IS NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_positions_account_ticker_current", table_name="positions")
