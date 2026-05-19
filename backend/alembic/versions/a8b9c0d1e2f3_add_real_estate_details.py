"""add_real_estate_details

Revision ID: a8b9c0d1e2f3
Revises: f1a2b3c4d5e6
Create Date: 2026-05-18 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "asset_accounts",
        sa.Column("real_estate_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("asset_accounts", "real_estate_details")
