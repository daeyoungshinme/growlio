"""add retirement_target_year to user_settings

Revision ID: 005
Revises: 004
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("retirement_target_year", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "retirement_target_year")
