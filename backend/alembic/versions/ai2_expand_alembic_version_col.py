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
    # growlio는 이제 `growlio_alembic_version`(alembic/env.py VERSION_TABLE)을 쓴다.
    # 완전 신규 DB를 처음부터 빌드하면 `alembic_version` 이라는 이름의 테이블은 생기지
    # 않으므로 IF EXISTS 로 방어한다. 기존 실 DB에는 그대로 적용된다.
    op.execute("ALTER TABLE IF EXISTS alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)")
