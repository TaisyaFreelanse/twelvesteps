"""add frame tracking

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2025-01-27 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create frame_tracking table for frame metadata and confirmation tracking."""
    from sqlalchemy import inspect
    
    # Check if table already exists
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'frame_tracking' not in existing_tables:
        op.create_table(
            'frame_tracking',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('confirmed', sa.JSON(), nullable=True),  # JSON массив подтвержденных фреймов
            sa.Column('candidates', sa.JSON(), nullable=True),  # JSON массив кандидатов
            sa.Column('tracking', sa.JSON(), nullable=True),  # JSON: repetition_count объект, min_to_confirm число
            sa.Column('archetypes', sa.JSON(), nullable=True),  # JSON массив архетипов: victim, rescuer, judge и т.д.
            sa.Column('meta_flags', sa.JSON(), nullable=True),  # JSON массив: loop_detected, frame_shift, identity_conflict
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_frame_tracking_user_id'), 'frame_tracking', ['user_id'], unique=False)
        op.create_index(op.f('ix_frame_tracking_id'), 'frame_tracking', ['id'], unique=False)


def downgrade() -> None:
    """Drop frame_tracking table."""
    op.drop_index(op.f('ix_frame_tracking_id'), table_name='frame_tracking')
    op.drop_index(op.f('ix_frame_tracking_user_id'), table_name='frame_tracking')
    op.drop_table('frame_tracking')

