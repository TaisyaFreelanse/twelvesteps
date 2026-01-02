from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'i6a7b8c9d0e1'
down_revision: Union[str, None] = 'h5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create tracker_summaries table for daily observation tracking."""
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'tracker_summaries' in existing_tables:
        return
    op.create_table(
        'tracker_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('thinking', sa.JSON(), nullable=True),
        sa.Column('feeling', sa.JSON(), nullable=True),
        sa.Column('behavior', sa.JSON(), nullable=True),
        sa.Column('relationships', sa.JSON(), nullable=True),
        sa.Column('health', sa.JSON(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='uq_tracker_summary_user_date')
    )
    op.create_index(op.f('ix_tracker_summaries_user_id'), 'tracker_summaries', ['user_id'], unique=False)
    op.create_index(op.f('ix_tracker_summaries_date'), 'tracker_summaries', ['date'], unique=False)
    op.create_index(op.f('ix_tracker_summaries_id'), 'tracker_summaries', ['id'], unique=False)


def downgrade() -> None:
    """Drop tracker_summaries table."""
    op.drop_index(op.f('ix_tracker_summaries_id'), table_name='tracker_summaries')
    op.drop_index(op.f('ix_tracker_summaries_date'), table_name='tracker_summaries')
    op.drop_index(op.f('ix_tracker_summaries_user_id'), table_name='tracker_summaries')
    op.drop_table('tracker_summaries')

