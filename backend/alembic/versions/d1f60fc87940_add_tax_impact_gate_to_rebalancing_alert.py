"""add tax impact gate to rebalancing alert

Revision ID: d1f60fc87940
Revises: 314d148b8f35
Create Date: 2026-07-21 11:11:53.495292

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1f60fc87940"
down_revision: str | None = "314d148b8f35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column("tax_impact_gate_mode", sa.String(length=10), server_default="DISABLED", nullable=False),
    )
    op.add_column("rebalancing_alerts", sa.Column("max_tax_impact_krw", sa.Numeric(precision=18, scale=2)))


def downgrade() -> None:
    op.drop_column("rebalancing_alerts", "max_tax_impact_krw")
    op.drop_column("rebalancing_alerts", "tax_impact_gate_mode")
