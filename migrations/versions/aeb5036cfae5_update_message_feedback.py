"""update message_feedback

Revision ID: aeb5036cfae5
Revises: 071da0bbb61b
Create Date: 2026-09-01 18:37:09.440665+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = 'aeb5036cfae5'
down_revision: Union[str, Sequence[str], None] = '071da0bbb61b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message_feedback",
        sa.Column("message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("owner_external_id", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint(
            "owner_external_id",
            "message_id",
            name="pk_message_feedback",
        ),
    )

def downgrade() -> None:
    op.drop_table("message_feedback")
