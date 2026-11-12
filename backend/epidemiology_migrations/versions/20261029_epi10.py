"""Append-only complementary staging and failure receipts."""
from pathlib import Path
from alembic import op
from sqlalchemy import text

revision = '20261029_epi10'
down_revision = '20261029_epi09'
branch_labels = None
depends_on = None


def upgrade():
    path = Path(__file__).resolve().parents[2] / 'database/epidemiology/006_ingestion_receipts.sql'
    op.get_bind().execute(text(path.read_text(encoding='utf-8')))
    # Existing accepted complements are already archived; populate staging from
    # normalized rows without reopening any source. Only aggregate/public data.
    op.execute('''INSERT INTO ingestion.fila_complementaria(lote_id,ordinal,contenido,sha256)
        SELECT lote_id,row_number() OVER(PARTITION BY lote_id ORDER BY payload::text),payload,
        encode(sha256(convert_to(payload::text,'UTF8')),'hex') FROM (
            SELECT lote_id,to_jsonb(c)-'lote_id' payload FROM epidemiology.clima_diario c
            UNION ALL SELECT lote_id,to_jsonb(a)-'lote_id' FROM epidemiology.agregado_publico a
            UNION ALL SELECT lote_id,to_jsonb(o)-'lote_id' FROM territory.observacion_censal o
        ) rows''')


def downgrade():
    raise RuntimeError('Destructive downgrade disabled')
