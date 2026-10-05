"""create messages feedback

Revision ID: 071da0bbb61b
Revises: 04038445ace9
Create Date: 2026-09-01 17:33:34.469118+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '071da0bbb61b'
down_revision: Union[str, Sequence[str], None] = '04038445ace9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'messages_feedback',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('owner_external_id', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'owner_external_id',
            'message_id',
            name='uq_messages_feedback_owner_message'
        )
    )


def downgrade() -> None:
    op.drop_table("messages_feedback")