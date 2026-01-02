from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'g4a5b6c7d8e9'
down_revision: Union[str, None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create qa_status table for quality assurance status tracking."""
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'qa_status' not in existing_tables:
        op.create_table(
            'qa_status',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('last_prompt_included', sa.Boolean(), nullable=True, server_default=sa.text('false')),
            sa.Column('trace_ok', sa.Boolean(), nullable=True, server_default=sa.text('false')),
            sa.Column('open_threads', sa.Integer(), nullable=True, server_default=sa.text('0')),
            sa.Column('rebuild_required', sa.Boolean(), nullable=True, server_default=sa.text('false')),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_qa_status_user_id'), 'qa_status', ['user_id'], unique=False)
        op.create_index(op.f('ix_qa_status_id'), 'qa_status', ['id'], unique=False)


def downgrade() -> None:
    """Drop qa_status table."""
    op.drop_index(op.f('ix_qa_status_id'), table_name='qa_status')
    op.drop_index(op.f('ix_qa_status_user_id'), table_name='qa_status')
    op.drop_table('qa_status')

