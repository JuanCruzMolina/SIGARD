"""Logical SISA rollback and aggregate availability gate."""
from pathlib import Path
from alembic import op
from sqlalchemy import text

revision = '20261029_epi11'
down_revision = '20261029_epi10'
branch_labels = None
depends_on = None


def upgrade():
    path = Path(__file__).resolve().parents[2] / 'database/epidemiology/007_batch_availability.sql'
    op.get_bind().execute(text(path.read_text(encoding='utf-8')))


def downgrade():
    raise RuntimeError('Destructive downgrade disabled')
