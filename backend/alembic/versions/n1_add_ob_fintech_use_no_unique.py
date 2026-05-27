"""Add unique constraint to ob_fintech_use_no to prevent duplicate open banking registrations

Revision ID: n1_ob_fintech_unique
Revises: m1_supabase_auth
Create Date: 2026-05-27
"""

from alembic import op

revision = "n1_ob_fintech_unique"
down_revision = "m1_supabase_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_asset_accounts_ob_fintech_use_no",
        "asset_accounts",
        ["ob_fintech_use_no"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_asset_accounts_ob_fintech_use_no",
        "asset_accounts",
        type_="unique",
    )
