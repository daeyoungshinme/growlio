"""add_rebalancing_alerts_active_mode_index

Revision ID: 717e507af8ab
Revises: ac1_add_portfolio_horizon_tax_type
Create Date: 2026-07-16 00:33:45.303452

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "717e507af8ab"
down_revision: str | None = "ac1_add_portfolio_horizon_tax_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("idx_rebalancing_alerts_active_mode", "rebalancing_alerts", ["is_active", "mode"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_rebalancing_alerts_active_mode", table_name="rebalancing_alerts")
