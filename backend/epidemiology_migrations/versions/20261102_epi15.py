"""Immutable stage-2 campaign registry, separate from frozen experiments."""
from pathlib import Path
from alembic import op
from sqlalchemy import text

revision='20261102_epi15'
down_revision='20261102_epi14'
branch_labels=None
depends_on=None


def upgrade():
    source=Path(__file__).resolve().parents[2]/'database/epidemiology/011_motor_registry.sql'
    op.get_bind().execute(text(source.read_text(encoding='utf-8')))


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; preserve research evidence')
