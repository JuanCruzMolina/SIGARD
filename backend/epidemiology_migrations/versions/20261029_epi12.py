"""Aggregate provenance and origin support for PostgreSQL-only ML readers."""
from pathlib import Path
from alembic import op

revision = '20261029_epi12'
down_revision = '20261029_epi11'
branch_labels = None
depends_on = None


def upgrade():
    path = Path(__file__).resolve().parents[2] / 'database/epidemiology/008_ml_consumers.sql'
    op.get_bind().exec_driver_sql(path.read_text(encoding='utf-8'))


def downgrade():
    raise RuntimeError('Destructive downgrade disabled')
