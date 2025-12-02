"""Add template_progress table for FSM template filling

Revision ID: k8a9b0c1d2e3
Revises: j7a8b9c0d1e2
Create Date: 2024-12-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'k8a9b0c1d2e3'
down_revision: Union[str, None] = 'j7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if enum type already exists
    result = conn.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'template_progress_status_enum'")
    )
    if not result.fetchone():
        op.execute("CREATE TYPE template_progress_status_enum AS ENUM ('IN_PROGRESS', 'PAUSED', 'COMPLETED', 'CANCELLED')")
    
    # Check if table already exists
    table_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'template_progress'")
    )
    if table_exists.fetchone():
        # Table already exists, skip creation
        return
    
    # Create template_progress table using raw SQL to avoid SQLAlchemy auto-creating enum
    op.execute("""
        CREATE TABLE template_progress (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            step_id INTEGER NOT NULL REFERENCES steps(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES step_questions(id) ON DELETE CASCADE,
            status template_progress_status_enum NOT NULL DEFAULT 'IN_PROGRESS',
            current_situation INTEGER NOT NULL DEFAULT 1,
            current_field VARCHAR(50) NOT NULL DEFAULT 'where',
            situations JSONB,
            conclusion TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            paused_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT uq_template_progress_user_step_question UNIQUE (user_id, step_id, question_id)
        )
    """)
    
    # Create indexes
    op.execute("CREATE INDEX IF NOT EXISTS ix_template_progress_user_id ON template_progress (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_template_progress_step_id ON template_progress (step_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_template_progress_question_id ON template_progress (question_id)")


def downgrade() -> None:
    # Drop table (indexes will be dropped automatically)
    op.execute("DROP TABLE IF EXISTS template_progress")
    
    # Drop enum type
    op.execute("DROP TYPE IF EXISTS template_progress_status_enum")
