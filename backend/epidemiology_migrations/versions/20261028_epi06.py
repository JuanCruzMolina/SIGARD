"""Prevent universe/calendar mixing and expose aggregate provenance safely."""
from alembic import op
revision='20261028_epi06'
down_revision='20261028_epi05'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql('''
    CREATE FUNCTION analytics.check_count_scope() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NOT EXISTS(SELECT 1 FROM analytics.ejecucion e JOIN territory.miembro_universo m ON m.universo_id=e.universo_id
        JOIN analytics.semana_epidemiologica w ON w.calendario_version=e.calendario_version
        WHERE e.id=NEW.ejecucion_id AND m.radio_id=NEW.radio_id AND w.id=NEW.semana_id
          AND w.inicio<=e.fin AND w.fin>=e.inicio
          AND NEW.ventana_parcial=(w.inicio<e.inicio OR w.fin>e.fin))
      THEN RAISE EXCEPTION 'count_universe_calendar_or_interval_mismatch'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER counts_scope_consistent BEFORE INSERT OR UPDATE ON analytics.conteos_radio_semana
      FOR EACH ROW EXECUTE FUNCTION analytics.check_count_scope();
    CREATE FUNCTION territory.check_universe_geometry() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      PERFORM 1 FROM territory.universo WHERE id=NEW.universo_id FOR UPDATE;
      IF EXISTS(SELECT 1 FROM territory.miembro_universo m JOIN territory.radio_censal old ON old.id=m.radio_id
        JOIN territory.radio_censal new ON new.id=NEW.radio_id
        WHERE m.universo_id=NEW.universo_id AND old.version_geometria_id<>new.version_geometria_id)
      THEN RAISE EXCEPTION 'universe_geometry_versions_mixed'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER universe_geometry_consistent BEFORE INSERT OR UPDATE ON territory.miembro_universo
      FOR EACH ROW EXECUTE FUNCTION territory.check_universe_geometry();
    CREATE VIEW analytics.conteos_con_procedencia AS
      SELECT c.*,r.codigo radio_codigo,w.inicio semana_inicio,w.fin semana_fin,w.anio,w.numero,
        e.version dataset_version,u.version universo_version,pt.version politica_temporal,
        pc.version politica_clasificacion,pc.definicion definicion_registros,
        CASE WHEN classes.n=1 THEN classes.codigo END clasificacion_epidemiologica,
        e.calendario_version,e.modo,e.equivalencia_ml_verificada,
        'source_records_not_accredited_episodes'::text unidad
      FROM analytics.conteos_radio_semana c JOIN analytics.ejecucion e ON e.id=c.ejecucion_id
      JOIN territory.radio_censal r ON r.id=c.radio_id JOIN territory.universo u ON u.id=e.universo_id
      JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
      JOIN epidemiology.politica_temporal pt ON pt.id=e.politica_temporal_id
      JOIN epidemiology.politica_clasificacion pc ON pc.id=e.politica_clasificacion_id
      CROSS JOIN LATERAL (SELECT count(*) n,min(cc.codigo) codigo FROM epidemiology.clase_admitida ca
        JOIN epidemiology.catalogo_clasificacion cc ON cc.id=ca.catalogo_id WHERE ca.politica_id=pc.id) classes;
    REVOKE ALL ON analytics.candidatos_espaciales_pendientes,analytics.exclusion_registro FROM sigard_epi_analytics_reader;
    GRANT SELECT ON analytics.conteos_con_procedencia TO sigard_epi_importer,sigard_epi_analytics_reader;
    REVOKE ALL ON FUNCTION analytics.check_count_scope(),territory.check_universe_geometry() FROM PUBLIC;
    ''')

def downgrade():raise RuntimeError('Destructive downgrade disabled')
