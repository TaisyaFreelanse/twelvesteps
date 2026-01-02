"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'ce8ae080e042'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('users')]

    try:
        op.alter_column('frames', 'user_id',
                   existing_type=sa.INTEGER(),
                   nullable=False)
    except Exception:
        pass

    if 'username' not in existing_columns:
        op.add_column('users', sa.Column('username', sa.String(length=255), nullable=True))
    if 'first_name' not in existing_columns:
        op.add_column('users', sa.Column('first_name', sa.String(length=255), nullable=True))
    if 'display_name' not in existing_columns:
        op.add_column('users', sa.Column('display_name', sa.String(length=255), nullable=True))
    if 'program_experience' not in existing_columns:
        op.add_column('users', sa.Column('program_experience', sa.String(length=64), nullable=True))
    if 'sobriety_date' not in existing_columns:
        op.add_column('users', sa.Column('sobriety_date', sa.Date(), nullable=True))
    if 'created_at' not in existing_columns:
        op.add_column('users', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    if 'updated_at' not in existing_columns:
        op.add_column('users', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    try:
        op.alter_column('users', 'telegram_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.String(length=64),
                   existing_nullable=True)
    except Exception:
        pass

    if 'registration_date' in existing_columns:
        op.drop_column('users', 'registration_date')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('registration_date', postgresql.TIMESTAMP(), server_default=sa.text("timezone('utc'::text, now())"), autoincrement=False, nullable=True))
    op.alter_column('users', 'telegram_id',
               existing_type=sa.String(length=64),
               type_=sa.INTEGER(),
               existing_nullable=True)
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'sobriety_date')
    op.drop_column('users', 'program_experience')
    op.drop_column('users', 'display_name')
    op.drop_column('users', 'first_name')
    op.drop_column('users', 'username')
    op.alter_column('frames', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=True)
