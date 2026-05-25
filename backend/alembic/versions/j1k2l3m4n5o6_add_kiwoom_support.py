"""add_kiwoom_support

Revision ID: j1k2l3m4n5o6
Revises: i1j2k3l4m5n6
Create Date: 2026-05-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, None] = "i1j2k3l4m5n6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # asset_accounts: 키움 계좌 필드 추가
    op.add_column("asset_accounts", sa.Column("kiwoom_account_no", sa.String(20), nullable=True))
    op.add_column("asset_accounts", sa.Column("kiwoom_app_key", sa.String(512), nullable=True))
    op.add_column("asset_accounts", sa.Column("kiwoom_app_secret", sa.String(512), nullable=True))

    # kiwoom_tokens 테이블 신규 생성 (키움은 계좌별 자격증명만 — account_id NOT NULL)
    op.create_table(
        "kiwoom_tokens",
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
        sa.Column("is_mock_mode", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # account_id unique (키움은 계좌 하나당 토큰 하나)
    op.create_index("uq_kiwoom_token_account", "kiwoom_tokens", ["account_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_kiwoom_token_account", table_name="kiwoom_tokens")
    op.drop_table("kiwoom_tokens")
    op.drop_column("asset_accounts", "kiwoom_app_secret")
    op.drop_column("asset_accounts", "kiwoom_app_key")
    op.drop_column("asset_accounts", "kiwoom_account_no")
