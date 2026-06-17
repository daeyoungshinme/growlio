"""Add fcm_token column to user_settings for FCM push notifications

Revision ID: af1_add_fcm_token
Revises: ae1_add_monthly_report_enabled
Create Date: 2026-06-09
"""

import sqlalchemy as sa

from alembic import op

revision = "af1_add_fcm_token"
down_revision = "ae1_add_monthly_report_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("fcm_token", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("user_settings", "fcm_token")
