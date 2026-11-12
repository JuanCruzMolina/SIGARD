"""Private normalized epidemiological schemas, additive and independent of API migrations."""
from pathlib import Path
from alembic import op

revision='20261028_epi01'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    sql=Path(__file__).resolve().parents[2]/'database/epidemiology/001_schema.sql'
    op.get_bind().exec_driver_sql(sql.read_text(encoding='utf-8'))

def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore only an explicitly owned disposable database')
