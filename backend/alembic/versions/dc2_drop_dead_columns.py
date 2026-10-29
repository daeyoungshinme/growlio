"""죽은 컬럼 드롭 — asset_snapshots.amount_original, kis/kiwoom/toss_tokens.token_type

모델·코드 참조는 dc1과 같은 배포(plans/91 G1-1)에서 이미 제거했다. Render preDeploy가 이 마이그레이션을
먼저 돌리는 동안 옛 인스턴스의 SELECT가 컬럼을 참조하지 않도록, 반드시 G1-1 배포가 끝난 뒤 머지한다.
downgrade는 컬럼만 되살린다(기존 값은 복원하지 않음, token_type은 server_default로 채움).

Revision ID: dc2_drop_dead_columns
Revises: dc1_drop_user_ticker_settings
Create Date: 2026-10-29 21:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "dc2_drop_dead_columns"
down_revision = "dc1_drop_user_ticker_settings"
branch_labels = None
depends_on = None

_TOKEN_TABLES = ("kis_tokens", "kiwoom_tokens", "toss_tokens")


def upgrade() -> None:
    op.drop_column("asset_snapshots", "amount_original")
    for table in _TOKEN_TABLES:
        op.drop_column(table, "token_type")


def downgrade() -> None:
    for table in _TOKEN_TABLES:
        op.add_column(table, sa.Column("token_type", sa.String(50), nullable=False, server_default="Bearer"))
    op.add_column("asset_snapshots", sa.Column("amount_original", sa.Numeric(18, 2), nullable=True))
