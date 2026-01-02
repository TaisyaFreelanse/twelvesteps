from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'k8a9b0c1d2e3'
down_revision: Union[str, None] = 'j7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'template_progress_status_enum'")
    )
    if not result.fetchone():
        op.execute("CREATE TYPE template_progress_status_enum AS ENUM ('IN_PROGRESS', 'PAUSED', 'COMPLETED', 'CANCELLED')")

    table_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'template_progress'")
    )
    if table_exists.fetchone():
        return

    op.create_table(
        'template_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('step_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('IN_PROGRESS', 'PAUSED', 'COMPLETED', 'CANCELLED', name='template_progress_status_enum'), nullable=False, server_default='IN_PROGRESS'),
        sa.Column('current_field', sa.String(100), nullable=True),
        sa.Column('filled_fields', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['step_id'], ['steps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['step_questions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['answer_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_template_progress_user_id ON template_progress (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_template_progress_step_id ON template_progress (step_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_template_progress_question_id ON template_progress (question_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS template_progress")

    op.execute("DROP TYPE IF EXISTS template_progress_status_enum")
