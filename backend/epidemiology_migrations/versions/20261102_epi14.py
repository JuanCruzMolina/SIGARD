"""Shared historical research dataset; no import, model or historical rewrite."""
from pathlib import Path
from alembic import op
from sqlalchemy import text

revision = '20261102_epi14'
down_revision = '20261029_epi13'
branch_labels = None
depends_on = None


def upgrade():
    path = Path(__file__).resolve().parents[2] / 'database/epidemiology/010_consolidation.sql'
    op.get_bind().execute(text(path.read_text(encoding='utf-8')))


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; historical sources must be preserved')
