from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'merge_heads_001'
down_revision: Union[str, Sequence[str], None] = ('34a07d00de7c', 'i6a7b8c9d0e1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge multiple migration heads."""
    pass


def downgrade() -> None:
    """Downgrade merge."""
    pass

