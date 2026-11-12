"""Cross-table integrity and source/unassigned reconciliation views."""
from pathlib import Path
from alembic import op
revision='20261028_epi03'
down_revision='20261028_epi02'
branch_labels=None
depends_on=None

def upgrade():
    path=Path(__file__).resolve().parents[2]/'database/epidemiology/003_integrity.sql'
    op.get_bind().exec_driver_sql(path.read_text(encoding='utf-8'))

def downgrade():
    raise RuntimeError('Destructive downgrade disabled')
