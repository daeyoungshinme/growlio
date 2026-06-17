"""add_provider_fields

Revision ID: 002
Revises: 001
Create Date: 2025-01-01 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # user_settings: LS증권 자격증명 + 오픈뱅킹 추가 필드
    op.add_column("user_settings", sa.Column("ls_app_key", sa.String(512), nullable=True))
    op.add_column("user_settings", sa.Column("ls_app_secret", sa.String(512), nullable=True))
    op.add_column(
        "user_settings",
        sa.Column("ls_is_mock", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column("user_settings", sa.Column("ob_refresh_token", sa.Text(), nullable=True))
    op.add_column("user_settings", sa.Column("ob_user_seq_no", sa.String(20), nullable=True))

    # asset_accounts: LS증권 계좌번호
    op.add_column("asset_accounts", sa.Column("ls_account_no", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("asset_accounts", "ls_account_no")
    op.drop_column("user_settings", "ob_user_seq_no")
    op.drop_column("user_settings", "ob_refresh_token")
    op.drop_column("user_settings", "ls_is_mock")
    op.drop_column("user_settings", "ls_app_secret")
    op.drop_column("user_settings", "ls_app_key")
