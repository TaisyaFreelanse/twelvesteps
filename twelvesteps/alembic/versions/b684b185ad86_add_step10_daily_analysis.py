"""add_step10_daily_analysis

Revision ID: b684b185ad86
Revises: k8a9b0c1d2e3
Create Date: 2025-12-02 17:08:02.924143

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b684b185ad86'
down_revision: Union[str, Sequence[str], None] = 'k8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if enum type already exists
    result = conn.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'step10_analysis_status_enum'")
    )
    if not result.fetchone():
        op.execute("CREATE TYPE step10_analysis_status_enum AS ENUM ('IN_PROGRESS', 'PAUSED', 'COMPLETED')")
    
    # Check if table already exists
    table_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'step10_daily_analysis'")
    )
    if table_exists.fetchone():
        # Table already exists, skip creation
        return
    
    # Create step10_daily_analysis table using raw SQL
    op.execute("""
        CREATE TABLE step10_daily_analysis (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            analysis_date DATE NOT NULL,
            status step10_analysis_status_enum NOT NULL DEFAULT 'IN_PROGRESS',
            current_question INTEGER NOT NULL DEFAULT 1,
            answers JSONB DEFAULT '[]'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            paused_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT uq_step10_analysis_user_date UNIQUE (user_id, analysis_date)
        )
    """)
    
    # Create indexes
    op.execute("CREATE INDEX IF NOT EXISTS ix_step10_daily_analysis_user_id ON step10_daily_analysis (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_step10_daily_analysis_date ON step10_daily_analysis (analysis_date)")


def downgrade() -> None:
    # Drop table (indexes will be dropped automatically)
    op.execute("DROP TABLE IF EXISTS step10_daily_analysis")
    
    # Drop enum type
    op.execute("DROP TYPE IF EXISTS step10_analysis_status_enum")
