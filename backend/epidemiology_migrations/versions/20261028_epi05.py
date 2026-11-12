"""Guard derived counts against partial analysis weeks and contradictory presence."""
from alembic import op
revision='20261028_epi05'
down_revision='20261028_epi04'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql('''
    ALTER TABLE analytics.conteos_radio_semana ADD COLUMN ventana_parcial boolean NOT NULL DEFAULT false;
    UPDATE analytics.conteos_radio_semana c SET ventana_parcial=true FROM analytics.ejecucion e,analytics.semana_epidemiologica w
      WHERE c.ejecucion_id=e.id AND c.semana_id=w.id AND (w.inicio<e.inicio OR w.fin>e.fin);
    ALTER TABLE analytics.conteos_radio_semana ADD CONSTRAINT count_no_approximate_or_partial
      CHECK(cantidad_registros IS NULL OR (fechas_aproximadas=0 AND NOT ventana_parcial));
    ALTER TABLE analytics.conteos_radio_semana ADD CONSTRAINT count_observed_consistent
      CHECK(cantidad_registros IS NULL OR (cantidad_registros=registros_observados AND presencia IS NOT NULL));
    ALTER TABLE analytics.conteos_radio_semana ADD CONSTRAINT presence_evidence_consistent
      CHECK(presencia IS NULL OR (presencia=1 AND registros_observados>0)
        OR (presencia=0 AND cantidad_registros IS NOT NULL AND cantidad_registros=0));
    ''')

def downgrade():raise RuntimeError('Destructive downgrade disabled')
