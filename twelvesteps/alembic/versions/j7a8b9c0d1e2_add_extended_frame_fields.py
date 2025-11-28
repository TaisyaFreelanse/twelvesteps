"""add extended frame fields

Revision ID: j7a8b9c0d1e2
Revises: merge_heads_001
Create Date: 2025-01-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'j7a8b9c0d1e2'
down_revision: Union[str, None] = 'merge_heads_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add extended fields to frames table for enhanced framing."""
    from sqlalchemy import inspect
    
    # Check if columns already exist before adding them
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('frames')]
    
    # Add new columns to frames table only if they don't exist
    if 'thinking_frame' not in existing_columns:
        op.add_column('frames', sa.Column('thinking_frame', sa.String(255), nullable=True))
    if 'level_of_mind' not in existing_columns:
        op.add_column('frames', sa.Column('level_of_mind', sa.Integer(), nullable=True))
    if 'memory_type' not in existing_columns:
        op.add_column('frames', sa.Column('memory_type', sa.String(50), nullable=True))
    if 'target_block' not in existing_columns:
        op.add_column('frames', sa.Column('target_block', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    if 'action' not in existing_columns:
        op.add_column('frames', sa.Column('action', sa.String(255), nullable=True))
    if 'strategy_hint' not in existing_columns:
        op.add_column('frames', sa.Column('strategy_hint', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove extended fields from frames table."""
    op.drop_column('frames', 'strategy_hint')
    op.drop_column('frames', 'action')
    op.drop_column('frames', 'target_block')
    op.drop_column('frames', 'memory_type')
    op.drop_column('frames', 'level_of_mind')
    op.drop_column('frames', 'thinking_frame')

