"""add_gratitudes_table

Revision ID: 923952692b61
Revises: b684b185ad86
Create Date: 2025-12-08 10:21:23.468716

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '923952692b61'
down_revision: Union[str, Sequence[str], None] = 'b684b185ad86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if table already exists
    table_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'gratitudes'")
    )
    if table_exists.fetchone():
        # Table already exists, skip creation
        return
    
    # Create gratitudes table using raw SQL
    op.execute("""
        CREATE TABLE gratitudes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    
    # Create indexes
    op.execute("CREATE INDEX IF NOT EXISTS ix_gratitudes_user_id ON gratitudes (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_gratitudes_created_at ON gratitudes (created_at)")


def downgrade() -> None:
    # Drop table (indexes will be dropped automatically)
    op.execute("DROP TABLE IF EXISTS gratitudes")
