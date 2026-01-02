from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b684b185ad86'
down_revision: Union[str, Sequence[str], None] = 'k8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'step10_analysis_status_enum'")
    )
    if not result.fetchone():
        op.execute("CREATE TYPE step10_analysis_status_enum AS ENUM ('IN_PROGRESS', 'PAUSED', 'COMPLETED')")

    table_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'step10_daily_analysis'")
    )
    if table_exists.fetchone():
        return

    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_step10_daily_analysis_user_id ON step10_daily_analysis (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_step10_daily_analysis_date ON step10_daily_analysis (analysis_date)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS step10_daily_analysis")

    op.execute("DROP TYPE IF EXISTS step10_analysis_status_enum")
