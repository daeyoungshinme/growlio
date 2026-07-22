"""add app_state table

Revision ID: 51e994cacfd1
Revises: d1f60fc87940
Create Date: 2026-07-22 22:09:33.547194

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "51e994cacfd1"
down_revision: str | None = "d1f60fc87940"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_state",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_state")
