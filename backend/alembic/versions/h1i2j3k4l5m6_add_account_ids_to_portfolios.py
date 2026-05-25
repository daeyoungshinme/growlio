"""add_account_ids_to_portfolios

portfolios 테이블에 리밸런싱 분석 대상 계좌 목록(account_ids) 컬럼 추가.

Revision ID: h1i2j3k4l5m6
Revises: g1h2i3j4k5l6
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("account_ids", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("portfolios", "account_ids")
