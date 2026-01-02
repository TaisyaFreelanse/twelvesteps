"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2d985e1a5f02'
down_revision: Union[str, Sequence[str], None] = 'ce8ae080e042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
