"""remove_ls_securities

LS증권 미구현 상태의 관련 컬럼 전부 제거.

Revision ID: g1h2i3j4k5l6
Revises: f9a8b7c6d5e4
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "f9a8b7c6d5e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # asset_accounts.ls_account_no 제거
    op.drop_column("asset_accounts", "ls_account_no")

    # user_settings의 LS 자격증명 컬럼 제거 (002 마이그레이션에서 추가된 컬럼)
    # 컬럼이 없으면 무시 (이미 제거된 환경 고려)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    us_cols = {c["name"] for c in inspector.get_columns("user_settings")}
    if "ls_app_key" in us_cols:
        op.drop_column("user_settings", "ls_app_key")
    if "ls_app_secret" in us_cols:
        op.drop_column("user_settings", "ls_app_secret")
    if "ls_is_mock" in us_cols:
        op.drop_column("user_settings", "ls_is_mock")


def downgrade() -> None:
    op.add_column("asset_accounts", sa.Column("ls_account_no", sa.String(20), nullable=True))
    op.add_column("user_settings", sa.Column("ls_app_key", sa.String(512), nullable=True))
    op.add_column("user_settings", sa.Column("ls_app_secret", sa.String(512), nullable=True))
    op.add_column("user_settings", sa.Column("ls_is_mock", sa.Boolean(), nullable=False, server_default="true"))
