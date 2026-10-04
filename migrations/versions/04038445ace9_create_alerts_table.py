"""create_alerts_table

Revision ID: 04038445ace9
Revises: d174e8d7d964
Create Date: 2026-08-29 13:58:02.999037+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '04038445ace9'
down_revision: Union[str, Sequence[str], None] = 'd174e8d7d964'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    #1. Создаем таблицу alerts
    # 1. Создание таблицы alerts
    op.create_table(
        'alerts',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('kind', sa.String(length=255), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('acked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Создаем частичный индекс для оптимизации очереди
    op.create_index(
        'idx_alerts_pending_created_at',
        'alerts',
        ['created_at'],
        unique=False,
        postgresql_where=sa.text('acked_at IS NULL')
    )


def downgrade() -> None:
    op.drop_index('idx_alerts_pending_created_at', table_name='alerts')
    op.drop_table('alerts')
