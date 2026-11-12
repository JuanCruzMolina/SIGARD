"""Single private predictive component and reusable complementary ingestion."""
from pathlib import Path
from alembic import op
from sqlalchemy import text

revision = '20261029_epi09'
down_revision = '20261028_epi08'
branch_labels = None
depends_on = None


def upgrade():
    path = Path(__file__).resolve().parents[2] / 'database/epidemiology/005_predictive_core.sql'
    op.get_bind().execute(text(path.read_text(encoding='utf-8')))


def downgrade():
    raise RuntimeError('Destructive downgrade disabled')
