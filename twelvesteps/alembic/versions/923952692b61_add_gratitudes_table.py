from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '923952692b61'
down_revision: Union[str, Sequence[str], None] = 'b684b185ad86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    table_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'gratitudes'")
    )
    if table_exists.fetchone():
        return

    op.create_table(
        'gratitudes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_gratitudes_user_id ON gratitudes (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_gratitudes_created_at ON gratitudes (created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gratitudes")
