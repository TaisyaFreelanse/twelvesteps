from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '2d985e1a5f02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('steps')]

    if 'title' not in existing_columns:
        op.add_column('steps', sa.Column('title', sa.String(255), nullable=True))
    if 'description' not in existing_columns:
        op.add_column('steps', sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('steps', 'description')
    op.drop_column('steps', 'title')

