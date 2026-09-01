"""add_toss_securities_support

Revision ID: f0551a2b3c4d
Revises: 17f4ddd81cae
Create Date: 2026-09-01

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f0551a2b3c4d"
down_revision: str | None = "17f4ddd81cae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # asset_accounts: 토스증권 계좌 필드 추가 (자격증명은 AES-256 암호문으로 저장)
    op.add_column("asset_accounts", sa.Column("toss_account_no", sa.String(20), nullable=True))
    op.add_column("asset_accounts", sa.Column("toss_client_id", sa.String(512), nullable=True))
    op.add_column("asset_accounts", sa.Column("toss_client_secret", sa.String(512), nullable=True))

    # toss_tokens 테이블 신규 생성 (토스는 계좌별 자격증명만 — account_id NOT NULL, 모의투자 없음)
    op.create_table(
        "toss_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("token_type", sa.String(50), nullable=False, server_default="Bearer"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("uq_toss_token_account", "toss_tokens", ["account_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_toss_token_account", table_name="toss_tokens")
    op.drop_table("toss_tokens")
    op.drop_column("asset_accounts", "toss_client_secret")
    op.drop_column("asset_accounts", "toss_client_id")
    op.drop_column("asset_accounts", "toss_account_no")
