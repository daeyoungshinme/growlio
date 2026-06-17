"""Supabase Auth migration: drop hashed_password, password_reset_tokens; add needs_password_reset

Revision ID: m1_supabase_auth
Revises: l1m2n3o4p5q6
Create Date: 2026-05-25

NOTE: Supabase DB에만 실행. 로컬 Docker DB에는 실행하지 말 것.
"""

import sqlalchemy as sa

from alembic import op

revision = "m1_supabase_auth"
down_revision = "l1m2n3o4p5q6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Supabase Auth가 password_reset_tokens 역할을 대체함
    op.drop_table("password_reset_tokens")

    # 기존 유저는 Supabase Auth로 이전 후 비밀번호 재설정 필요
    op.add_column(
        "users",
        sa.Column(
            "needs_password_reset",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # Supabase Auth가 비밀번호를 관리 (auth.users 테이블)
    op.drop_column("users", "hashed_password")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("hashed_password", sa.String(length=255), autoincrement=False, nullable=True),
    )
    op.drop_column("users", "needs_password_reset")
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("token_hash", sa.VARCHAR(length=64), autoincrement=False, nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("used", sa.Boolean(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
