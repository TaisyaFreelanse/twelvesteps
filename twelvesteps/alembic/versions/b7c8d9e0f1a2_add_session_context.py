from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    """))
    enum_exists = result.scalar()

    if not enum_exists:
        """)

    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'session_contexts' not in existing_tables:
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
    op.drop_index(op.f('ix_session_contexts_user_id'), table_name='session_contexts')
    op.drop_table('session_contexts')
    op.execute("DROP TYPE session_type_enum")

