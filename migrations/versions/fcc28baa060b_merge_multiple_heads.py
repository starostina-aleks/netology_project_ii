"""Merge multiple heads

Revision ID: fcc28baa060b
Revises: 2b80bdf48d6b, 8fee833aff5a
Create Date: 2026-10-23 06:37:14.608715+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fcc28baa060b'
down_revision: Union[str, Sequence[str], None] = ('2b80bdf48d6b', '8fee833aff5a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
