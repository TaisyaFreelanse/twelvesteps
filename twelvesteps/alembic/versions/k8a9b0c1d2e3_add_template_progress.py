"""Add template_progress table for FSM template filling

Revision ID: k8a9b0c1d2e3
Revises: j7a8b9c0d1e2
Create Date: 2024-12-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'k8a9b0c1d2e3'
down_revision: Union[str, None] = 'j7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type for template progress status
    template_progress_status_enum = postgresql.ENUM(
        'IN_PROGRESS', 'PAUSED', 'COMPLETED', 'CANCELLED',
        name='template_progress_status_enum',
        create_type=False
    )
    template_progress_status_enum.create(op.get_bind(), checkfirst=True)
    
    # Create template_progress table
    op.create_table(
        'template_progress',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('step_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('IN_PROGRESS', 'PAUSED', 'COMPLETED', 'CANCELLED', name='template_progress_status_enum'), 
                  server_default='IN_PROGRESS', nullable=False),
        sa.Column('current_situation', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('current_field', sa.String(50), nullable=False, server_default='where'),
        sa.Column('situations', sa.JSON(), nullable=True),
        sa.Column('conclusion', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['step_id'], ['steps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['step_questions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'step_id', 'question_id', name='uq_template_progress_user_step_question')
    )
    
    # Create indexes
    op.create_index('ix_template_progress_user_id', 'template_progress', ['user_id'])
    op.create_index('ix_template_progress_step_id', 'template_progress', ['step_id'])
    op.create_index('ix_template_progress_question_id', 'template_progress', ['question_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_template_progress_question_id', 'template_progress')
    op.drop_index('ix_template_progress_step_id', 'template_progress')
    op.drop_index('ix_template_progress_user_id', 'template_progress')
    
    # Drop table
    op.drop_table('template_progress')
    
    # Drop enum type
    op.execute("DROP TYPE IF EXISTS template_progress_status_enum")

