from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Integer, JSON, inspect, text

revision: str = '34a07d00de7c'
down_revision: Union[str, Sequence[str], None] = '0c9f04e7d5e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect, text

    conn = op.get_bind()
    """))
    enum_exists = result.scalar()

    if not enum_exists:
        op.execute("CREATE TYPE template_type_enum AS ENUM ('AUTHOR', 'CUSTOM')")

    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    existing_columns = [col['name'] for col in inspector.get_columns('users')] if 'users' in existing_tables else []

    if 'answer_templates' not in existing_tables:
        op.create_table(
            'answer_templates',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('template_type', sa.Enum('AUTHOR', 'CUSTOM', name='template_type_enum'), nullable=False),
            sa.Column('structure', sa.JSON(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_answer_templates_user_id'), 'answer_templates', ['user_id'], unique=False)

    if 'active_template_id' not in existing_columns:
        op.add_column('users', sa.Column('active_template_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'fk_users_active_template_id',
            'users', 'answer_templates',
            ['active_template_id'], ['id'],
            ondelete='SET NULL'
        )
        op.create_index(op.f('ix_users_active_template_id'), 'users', ['active_template_id'], unique=False)

    if 'answer_templates' not in existing_tables:
        answer_templates = table(
            'answer_templates',
            column('id', Integer),
            column('user_id', Integer),
            column('name', String),
            column('template_type', String),
            column('structure', JSON),
        )

        author_template_structure = {
            "situation": "Ситуация",
            "thoughts": "Мысли",
            "feelings_before": "Чувства (до)",
            "actions": "Действия",
            "feelings_after": "Чувства (после)",
            "exit_paths": "Пути выхода",
            "conclusion": "Вывод",
            "what_didnt_fit": "Что не попало"
        }

        op.bulk_insert(answer_templates, [
            {
                'id': 1,
                'user_id': None,
                'name': 'Авторский шаблон',
                'template_type': 'AUTHOR',
                'structure': author_template_structure
            }
        ])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_active_template_id'), table_name='users')
    op.drop_constraint('fk_users_active_template_id', 'users', type_='foreignkey')
    op.drop_column('users', 'active_template_id')
    op.drop_index(op.f('ix_answer_templates_user_id'), table_name='answer_templates')
    op.drop_table('answer_templates')
    op.execute("DROP TYPE template_type_enum")
