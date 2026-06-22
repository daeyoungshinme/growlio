"""drop_securities_table: Security 모델(종목 마스터) dead code 제거

Revision ID: aa1_drop_securities_table
Revises: z2_positions_normalization
Create Date: 2026-06-22

Securities 테이블은 생성 이후 한 번도 사용되지 않은 dead code.
"""

from alembic import op

revision = "aa1_drop_securities_table"
down_revision = "z2_positions_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_securities_ticker", table_name="securities")
    op.drop_index("idx_securities_market", table_name="securities")
    op.drop_table("securities")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "securities",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("name_ko", sa.String(200), nullable=True),
        sa.Column("name_en", sa.String(200), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("is_etf", sa.Boolean, default=False, nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("ticker", "market", name="uq_security_ticker_market"),
    )
    op.create_index("idx_securities_ticker", "securities", ["ticker"])
    op.create_index("idx_securities_market", "securities", ["market"])
