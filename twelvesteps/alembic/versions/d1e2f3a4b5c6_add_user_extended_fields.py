"""add user extended fields

Revision ID: d1e2f3a4b5c6
Revises: b7c8d9e0f1a2
Create Date: 2025-01-27 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add extended fields to users table."""
    from sqlalchemy import inspect
    
    # Check if columns already exist before adding them
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Add relapse_dates (JSON array of dates in YYYY-MM-DD format)
    if 'relapse_dates' not in existing_columns:
        op.add_column('users', sa.Column('relapse_dates', sa.JSON(), nullable=True))
    
    # Add sponsor_ids (JSON array of sponsor IDs)
    if 'sponsor_ids' not in existing_columns:
        op.add_column('users', sa.Column('sponsor_ids', sa.JSON(), nullable=True))
    
    # Add custom_fields (JSON for goals, important people, support format)
    if 'custom_fields' not in existing_columns:
        op.add_column('users', sa.Column('custom_fields', sa.JSON(), nullable=True))
    
    # Add last_active (timestamp, updated on each interaction)
    if 'last_active' not in existing_columns:
        op.add_column('users', sa.Column('last_active', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove extended fields from users table."""
    op.drop_column('users', 'last_active')
    op.drop_column('users', 'custom_fields')
    op.drop_column('users', 'sponsor_ids')
    op.drop_column('users', 'relapse_dates')

