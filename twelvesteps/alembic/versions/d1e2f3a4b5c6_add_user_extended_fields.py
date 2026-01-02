"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add extended fields to users table."""
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('users')]

    if 'relapse_dates' not in existing_columns:
        op.add_column('users', sa.Column('relapse_dates', sa.JSON(), nullable=True))

    if 'sponsor_ids' not in existing_columns:
        op.add_column('users', sa.Column('sponsor_ids', sa.JSON(), nullable=True))

    if 'custom_fields' not in existing_columns:
        op.add_column('users', sa.Column('custom_fields', sa.JSON(), nullable=True))

    if 'last_active' not in existing_columns:
        op.add_column('users', sa.Column('last_active', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove extended fields from users table."""
    op.drop_column('users', 'last_active')
    op.drop_column('users', 'custom_fields')
    op.drop_column('users', 'sponsor_ids')
    op.drop_column('users', 'relapse_dates')

