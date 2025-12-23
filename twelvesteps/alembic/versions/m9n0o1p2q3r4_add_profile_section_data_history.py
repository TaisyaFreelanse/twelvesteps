"""add_profile_section_data_history

Revision ID: m9n0o1p2q3r4
Revises: k8a9b0c1d2e3
Create Date: 2025-01-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import String, Integer, Float, Boolean

# revision identifiers, used by Alembic.
revision: str = 'm9n0o1p2q3r4'
down_revision: Union[str, Sequence[str], None] = 'k8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add history and subblock fields to profile_section_data."""
    # Add new columns to profile_section_data table
    op.add_column('profile_section_data', 
        sa.Column('subblock_name', sa.String(length=255), nullable=True, comment='Название подблока (например, "Юрист", "Судья")')
    )
    op.add_column('profile_section_data',
        sa.Column('entity_type', sa.String(length=100), nullable=True, comment='Тип сущности (profession, role, relationship и т.п.)')
    )
    op.add_column('profile_section_data',
        sa.Column('importance', sa.Float(), nullable=True, server_default='1.0', comment='Важность записи (0.0-1.0)')
    )
    op.add_column('profile_section_data',
        sa.Column('is_core_personality', sa.Boolean(), nullable=False, server_default=sa.text('false'), comment='Входит ли в ядро личности')
    )
    op.add_column('profile_section_data',
        sa.Column('tags', sa.String(length=500), nullable=True, comment='Теги через запятую (эмоции, триггеры, тон)')
    )
    
    # Add index for faster queries by subblock
    op.create_index(
        'ix_profile_section_data_subblock',
        'profile_section_data',
        ['section_id', 'subblock_name'],
        unique=False
    )
    
    # Add index for core personality queries
    op.create_index(
        'ix_profile_section_data_core',
        'profile_section_data',
        ['user_id', 'is_core_personality'],
        unique=False
    )


def downgrade() -> None:
    """Remove history and subblock fields from profile_section_data."""
    op.drop_index('ix_profile_section_data_core', table_name='profile_section_data')
    op.drop_index('ix_profile_section_data_subblock', table_name='profile_section_data')
    op.drop_column('profile_section_data', 'tags')
    op.drop_column('profile_section_data', 'is_core_personality')
    op.drop_column('profile_section_data', 'importance')
    op.drop_column('profile_section_data', 'entity_type')
    op.drop_column('profile_section_data', 'subblock_name')

