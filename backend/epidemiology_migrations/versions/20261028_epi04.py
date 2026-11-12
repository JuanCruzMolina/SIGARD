"""Normalize census provenance and block unverified as-of static context."""
from pathlib import Path
from alembic import op
revision='20261028_epi04'
down_revision='20261028_epi03'
branch_labels=None
depends_on=None

def upgrade():
    db=op.get_bind()
    db.exec_driver_sql('''
    DO $$ BEGIN
     IF EXISTS(SELECT version FROM territory.contexto_censal GROUP BY version HAVING count(DISTINCT fuente_sha256)>1)
     THEN RAISE EXCEPTION 'census_version_provenance_conflict'; END IF;
    END $$;
    CREATE TABLE territory.version_contexto_censal(version text PRIMARY KEY,fuente_sha256 char(64) NOT NULL);
    INSERT INTO territory.version_contexto_censal SELECT DISTINCT version,fuente_sha256 FROM territory.contexto_censal;
    ALTER TABLE territory.contexto_censal ADD FOREIGN KEY(version) REFERENCES territory.version_contexto_censal(version);
    ALTER TABLE territory.contexto_censal DROP COLUMN fuente_sha256;
    GRANT SELECT,INSERT,UPDATE ON territory.version_contexto_censal TO sigard_epi_importer;
    CREATE INDEX ix_clasificacion_regla ON epidemiology.normalizacion_clasificacion(regla_id,observacion_id);
    CREATE INDEX ix_regla_catalogo ON epidemiology.regla_normalizacion_clasificacion(catalogo_id);
    ''')
    # Reuse the immutable v2 SQL definition, replacing ONLY static as-of exposure.
    source=(Path(__file__).resolve().parents[2]/'database/epidemiology/002_views.sql').read_text(encoding='utf-8')
    a=source[source.index('CREATE VIEW analytics.ml_a'):source.index('CREATE FUNCTION analytics.presencia_en')]
    v=source[source.index('CREATE VIEW analytics.ml_v3'):source.index('-- View rights')]
    guard="(e.modo='retrospective' OR (x.disponible_desde IS NOT NULL AND x.disponible_desde < (w.fin+1)::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires'))"
    old='x.superficie_km2,x.poblacion,x.poblacion/x.superficie_km2 densidad_poblacional,\n x.cantidad_vecinos'
    new=f'CASE WHEN {guard} THEN x.superficie_km2 END superficie_km2,CASE WHEN {guard} THEN x.poblacion END poblacion,CASE WHEN {guard} THEN x.poblacion/x.superficie_km2 END densidad_poblacional,\n CASE WHEN {guard} THEN x.cantidad_vecinos END cantidad_vecinos'
    assert old in a
    a=a.replace(old,new).replace('CREATE VIEW','CREATE OR REPLACE VIEW',1)
    old='x.poblacion population,x.poblacion/x.superficie_km2 population_density'
    assert old in v
    v=v.replace(old,f'CASE WHEN {guard} THEN x.poblacion END population,CASE WHEN {guard} THEN x.poblacion/x.superficie_km2 END population_density').replace('CREATE VIEW','CREATE OR REPLACE VIEW',1)
    db.exec_driver_sql(a);db.exec_driver_sql(v)

def downgrade():raise RuntimeError('Destructive downgrade disabled')
