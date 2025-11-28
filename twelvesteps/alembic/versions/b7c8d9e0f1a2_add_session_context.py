"""add session context

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2025-01-27 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create session_type enum only if it doesn't exist
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'session_type_enum'
        )
    """))
    enum_exists = result.scalar()
    
    if not enum_exists:
        op.execute("""
            CREATE TYPE session_type_enum AS ENUM ('STEPS', 'DAY', 'CHAT');
        """)
    
    # Check if table already exists
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'session_contexts' not in existing_tables:
        # Create session_contexts table
        op.create_table(
            'session_contexts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('session_type', postgresql.ENUM('STEPS', 'DAY', 'CHAT', name='session_type_enum', create_type=False), nullable=False),
            sa.Column('context_data', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_session_contexts_user_id'), 'session_contexts', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop table and enum
    op.drop_index(op.f('ix_session_contexts_user_id'), table_name='session_contexts')
    op.drop_table('session_contexts')
    op.execute("DROP TYPE session_type_enum")

