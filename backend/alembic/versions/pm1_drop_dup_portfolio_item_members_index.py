"""drop duplicate idx_portfolio_item_members_item

`portfolio_item_id` 단일 인덱스는 unique 제약 `uq_portfolio_item_members_key(portfolio_item_id, ticker, market)`의
선두 열과 같아 조회에 쓰이지 않고 쓰기 비용만 늘렸다(plans/77 이관 → plans/79 H).

Revision ID: pm1_drop_dup_portfolio_item_members_index
Revises: at1_widen_alert_history_alert_type
Create Date: 2026-10-27 12:00:00.000000

"""

from alembic import op

revision = "pm1_drop_dup_portfolio_item_members_index"
down_revision = "at1_widen_alert_history_alert_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_portfolio_item_members_item", table_name="portfolio_item_members")


def downgrade() -> None:
    op.create_index("idx_portfolio_item_members_item", "portfolio_item_members", ["portfolio_item_id"])
