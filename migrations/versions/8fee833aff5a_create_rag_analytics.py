"""create rag analytics

Revision ID: 8fee833aff5a
Revises: d174e8d7d964
Create Date: 2026-09-02 12:23:37.064273+00:00

"""
from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8fee833aff5a'
down_revision: Union[str, Sequence[str], None] = 'd174e8d7d964'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_queries",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("question_normalized", sa.Text(), nullable=False),
        sa.Column("confident", sa.Boolean(), nullable=False),
        sa.Column("top_score", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    # Покрывает и refusal_rate за окно, и группировку пробелов по неуверенным ответам.
    op.create_index(
        "idx_rag_queries_confident_created",
        "rag_queries",
        ["confident", "created_at"],
    )
    op.add_column("chat_messages", sa.Column("sources", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "sources")
    op.drop_index("idx_rag_queries_confident_created", table_name="rag_queries")
    op.drop_table("rag_queries")
