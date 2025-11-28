"""add session state

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2025-01-27 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create session_states table for operational state tracking."""
    op.create_table(
        'session_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('recent_messages', sa.JSON(), nullable=True),  # JSON массив с timestamp, text, tags
        sa.Column('daily_snapshot', sa.JSON(), nullable=True),  # JSON: emotions, triggers, actions, health
        sa.Column('active_blocks', sa.JSON(), nullable=True),  # JSON массив строк
        sa.Column('pending_topics', sa.JSON(), nullable=True),  # JSON массив строк
        sa.Column('group_signals', sa.JSON(), nullable=True),  # JSON массив строк
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_session_states_user_id'), 'session_states', ['user_id'], unique=False)
    op.create_index(op.f('ix_session_states_id'), 'session_states', ['id'], unique=False)


def downgrade() -> None:
    """Drop session_states table."""
    op.drop_index(op.f('ix_session_states_id'), table_name='session_states')
    op.drop_index(op.f('ix_session_states_user_id'), table_name='session_states')
    op.drop_table('session_states')

