"""add user meta

Revision ID: h5a6b7c8d9e0
Revises: g4a5b6c7d8e9
Create Date: 2025-01-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'h5a6b7c8d9e0'
down_revision: Union[str, None] = 'g4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create user_meta table for user system metadata (one-to-one with users)."""
    op.create_table(
        'user_meta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('metasloy_signals', sa.JSON(), nullable=True),  # JSON массив строк
        sa.Column('prompt_revision_history', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('time_zone', sa.String(length=50), nullable=True),  # string, например "UTC+3"
        sa.Column('language', sa.String(length=10), nullable=True, server_default='ru'),  # string, default='ru'
        sa.Column('data_flags', sa.JSON(), nullable=True),  # JSON: encrypted boolean, anonymized boolean, retention_days integer
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_user_meta_user_id')  # One-to-one relationship
    )
    op.create_index(op.f('ix_user_meta_user_id'), 'user_meta', ['user_id'], unique=True)
    op.create_index(op.f('ix_user_meta_id'), 'user_meta', ['id'], unique=False)


def downgrade() -> None:
    """Drop user_meta table."""
    op.drop_index(op.f('ix_user_meta_id'), table_name='user_meta')
    op.drop_index(op.f('ix_user_meta_user_id'), table_name='user_meta')
    op.drop_table('user_meta')

