"""remove_global_kis_from_user_settings

user_settings 테이블에서 전역 KIS 자격증명 컬럼 제거.
KIS 자격증명은 이제 asset_accounts 테이블에 계좌별로 저장한다.

Revision ID: l1m2n3o4p5q6
Revises: 6eafeed60ba3
Create Date: 2026-05-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l1m2n3o4p5q6"
down_revision: Union[str, None] = "6eafeed60ba3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("user_settings", "kis_app_key")
    op.drop_column("user_settings", "kis_app_secret")
    op.drop_column("user_settings", "kis_account_no")
    op.drop_column("user_settings", "kis_is_mock")


def downgrade() -> None:
    op.add_column("user_settings", sa.Column("kis_is_mock", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("user_settings", sa.Column("kis_account_no", sa.String(20), nullable=True))
    op.add_column("user_settings", sa.Column("kis_app_secret", sa.String(512), nullable=True))
    op.add_column("user_settings", sa.Column("kis_app_key", sa.String(512), nullable=True))
