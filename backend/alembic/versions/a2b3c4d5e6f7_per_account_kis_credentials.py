"""per_account_kis_credentials

Revision ID: a2b3c4d5e6f7
Revises: f9a8b7c6d5e4
Create Date: 2026-05-21 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f9a8b7c6d5e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # asset_accounts에 계좌별 KIS 자격증명 컬럼 추가
    op.add_column("asset_accounts", sa.Column("kis_app_key", sa.String(512), nullable=True))
    op.add_column("asset_accounts", sa.Column("kis_app_secret", sa.String(512), nullable=True))

    # kis_tokens에 account_id 컬럼 추가
    op.add_column(
        "kis_tokens",
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_accounts.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )

    # 기존 (user_id, is_mock_mode) unique constraint 제거
    op.drop_constraint("uq_kis_token_user_mode", "kis_tokens", type_="unique")

    # 유저 레벨 토큰: account_id IS NULL 조건의 partial unique index
    op.create_index(
        "uq_kis_token_user_mode",
        "kis_tokens",
        ["user_id", "is_mock_mode"],
        unique=True,
        postgresql_where=sa.text("account_id IS NULL"),
    )

    # 계좌 레벨 토큰: account_id IS NOT NULL 조건의 partial unique index
    op.create_index(
        "uq_kis_token_account",
        "kis_tokens",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("account_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_kis_token_account", "kis_tokens")
    op.drop_index("uq_kis_token_user_mode", "kis_tokens")

    # 기존 unique constraint 복원
    op.create_unique_constraint("uq_kis_token_user_mode", "kis_tokens", ["user_id", "is_mock_mode"])

    op.drop_column("kis_tokens", "account_id")
    op.drop_column("asset_accounts", "kis_app_secret")
    op.drop_column("asset_accounts", "kis_app_key")
