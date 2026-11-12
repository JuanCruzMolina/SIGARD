-- Reviews supplement original observations. They never UPDATE source values.
CREATE TABLE epidemiology.version_resolucion (
 version text PRIMARY KEY, politica text NOT NULL, entrada_sha256 char(64) NOT NULL,
 evidencia jsonb NOT NULL CHECK(jsonb_typeof(evidencia)='object'),
 creada_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE territory.revision_asignacion (
 version text REFERENCES epidemiology.version_resolucion,
 asignacion_id bigint REFERENCES territory.asignacion_radio,
 radio_id bigint REFERENCES territory.radio_censal,
 estado text NOT NULL CHECK(estado IN ('unique_provisional','point_only','ambiguous','boundary','outside','invalid','insufficient')),
 motivo text NOT NULL, comprobaciones jsonb NOT NULL,
 PRIMARY KEY(version,asignacion_id),
 CHECK((estado IN ('unique_provisional','point_only'))=(radio_id IS NOT NULL))
);
CREATE FUNCTION territory.check_revision_assignment() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.radio_id IS NOT NULL AND NOT EXISTS(
   SELECT 1 FROM territory.asignacion_radio a
   JOIN territory.geocodificacion g ON g.id=a.geocodificacion_id
   JOIN territory.radio_censal r ON r.id=NEW.radio_id AND r.version_geometria_id=a.version_geometria_id
   WHERE a.id=NEW.asignacion_id AND ST_Contains(r.geom,g.geom)
     AND (SELECT count(*) FROM territory.radio_censal other
       WHERE other.version_geometria_id=a.version_geometria_id AND ST_Intersects(other.geom,g.geom))=1)
 THEN RAISE EXCEPTION 'revision_radio_version_or_unique_interior_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER revision_assignment_consistent BEFORE INSERT ON territory.revision_asignacion
 FOR EACH ROW EXECUTE FUNCTION territory.check_revision_assignment();
CREATE TABLE epidemiology.revision_fecha (
 version text REFERENCES epidemiology.version_resolucion,
 fecha_id bigint REFERENCES epidemiology.fecha_registro,
 valor date, estado text NOT NULL CHECK(estado IN ('valid','missing','invalid_format','out_of_range')),
 motivo text NOT NULL, PRIMARY KEY(version,fecha_id), CHECK((estado='valid')=(valor IS NOT NULL))
);
CREATE TABLE epidemiology.revision_clasificacion (
 version text REFERENCES epidemiology.version_resolucion,
 observacion_id bigint REFERENCES epidemiology.clasificacion_registro,
 catalogo_id bigint REFERENCES epidemiology.catalogo_clasificacion,
 motivo text NOT NULL, PRIMARY KEY(version,observacion_id)
);
CREATE TABLE epidemiology.revision_extraccion (
 version text REFERENCES epidemiology.version_resolucion,
 archivo_id bigint REFERENCES ingestion.archivo_fuente,
 declaracion jsonb NOT NULL CHECK(jsonb_typeof(declaracion)='object'),
 PRIMARY KEY(version,archivo_id)
);
CREATE FUNCTION epidemiology.review_is_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'review_is_append_only_use_new_version'; END $$;
DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['epidemiology.version_resolucion','territory.revision_asignacion',
   'epidemiology.revision_fecha','epidemiology.revision_clasificacion','epidemiology.revision_extraccion'] LOOP
   EXECUTE format('CREATE TRIGGER review_immutable BEFORE UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION epidemiology.review_is_immutable()',item);
 END LOOP;
END $$;
ALTER TABLE analytics.ejecucion ADD COLUMN resolucion_version text REFERENCES epidemiology.version_resolucion;
-- Preserve every pre-existing column and append provenance to the public aggregate contract.
CREATE OR REPLACE VIEW analytics.conteos_con_procedencia AS
 SELECT c.*,r.codigo radio_codigo,w.inicio semana_inicio,w.fin semana_fin,w.anio,w.numero,
 e.version dataset_version,u.version universo_version,pt.version politica_temporal,
 pc.version politica_clasificacion,pc.definicion definicion_registros,
 CASE WHEN classes.n=1 THEN classes.codigo END clasificacion_epidemiologica,
 e.calendario_version,e.modo,e.equivalencia_ml_verificada,
 'source_records_not_accredited_episodes'::text unidad,
 e.resolucion_version version_resolucion_geografica,gv.version version_territorial,
 criterion.version politica_cobertura,
 ARRAY(SELECT a.sha256::text FROM analytics.fuente_ejecucion fe
   JOIN ingestion.lote_importacion l ON l.id=fe.lote_id
   JOIN ingestion.archivo_fuente a ON a.id=l.archivo_id
   WHERE fe.ejecucion_id=e.id ORDER BY a.id) fuentes_sha256
 FROM analytics.conteos_radio_semana c JOIN analytics.ejecucion e ON e.id=c.ejecucion_id
 JOIN territory.radio_censal r ON r.id=c.radio_id JOIN territory.universo u ON u.id=e.universo_id
 JOIN territory.version_geometria gv ON gv.id=r.version_geometria_id
 JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
 JOIN epidemiology.politica_temporal pt ON pt.id=e.politica_temporal_id
 JOIN epidemiology.politica_clasificacion pc ON pc.id=e.politica_clasificacion_id
 JOIN epidemiology.criterio_cobertura criterion ON criterion.id=e.criterio_cobertura_id
 CROSS JOIN LATERAL (SELECT count(*) n,min(cc.codigo) codigo FROM epidemiology.clase_admitida ca
   JOIN epidemiology.catalogo_clasificacion cc ON cc.id=ca.catalogo_id WHERE ca.politica_id=pc.id) classes;
REVOKE ALL ON epidemiology.version_resolucion,territory.revision_asignacion,
 epidemiology.revision_fecha,epidemiology.revision_clasificacion,epidemiology.revision_extraccion FROM PUBLIC;
GRANT SELECT,INSERT ON epidemiology.version_resolucion,territory.revision_asignacion,
 epidemiology.revision_fecha,epidemiology.revision_clasificacion,epidemiology.revision_extraccion TO sigard_epi_importer;
REVOKE ALL ON FUNCTION territory.check_revision_assignment(),epidemiology.review_is_immutable() FROM PUBLIC;
