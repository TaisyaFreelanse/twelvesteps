"""merge multiple heads

Revision ID: merge_heads_001
Revises: 34a07d00de7c, i6a7b8c9d0e1
Create Date: 2025-01-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'merge_heads_001'
down_revision: Union[str, Sequence[str], None] = ('34a07d00de7c', 'i6a7b8c9d0e1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge multiple migration heads."""
    # This is a merge migration - no schema changes needed
    pass


def downgrade() -> None:
    """Downgrade merge."""
    pass

