"""add_exchange_rate_alerts

Revision ID: f1a2b3c4d5e6
Revises: e8a93587d968
Create Date: 2026-05-18 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e8a93587d968'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 멱등 처리: 타입이 이미 존재하면 스킵 (이전 실패한 마이그레이션으로 부분 생성된 경우 대응)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE alert_direction_enum AS ENUM ('BELOW', 'ABOVE');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.create_table(
        'exchange_rate_alerts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('target_rate', sa.Numeric(10, 2), nullable=False),
        sa.Column('direction', postgresql.ENUM('BELOW', 'ABOVE', name='alert_direction_enum', create_type=False), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_exchange_rate_alerts_user_active', 'exchange_rate_alerts', ['user_id', 'is_active'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_exchange_rate_alerts_user_active', table_name='exchange_rate_alerts')
    op.drop_table('exchange_rate_alerts')
    op.execute("DROP TYPE IF EXISTS alert_direction_enum")
