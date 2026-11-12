-- Additional cross-table consistency; no rows or original values removed.
CREATE FUNCTION epidemiology.check_observation_column() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (SELECT hoja_id FROM ingestion.columna_fuente WHERE id=NEW.columna_id)
 IS DISTINCT FROM (SELECT s.hoja_id FROM ingestion.fila_staging s JOIN epidemiology.registro_epidemiologico r ON r.fila_id=s.id WHERE r.id=NEW.registro_id)
 THEN RAISE EXCEPTION 'observation_column_source_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER classification_source_consistent BEFORE INSERT OR UPDATE ON epidemiology.clasificacion_registro
 FOR EACH ROW EXECUTE FUNCTION epidemiology.check_observation_column();
CREATE TRIGGER date_source_consistent BEFORE INSERT OR UPDATE ON epidemiology.fecha_registro
 FOR EACH ROW EXECUTE FUNCTION epidemiology.check_observation_column();

CREATE FUNCTION territory.check_assignment_result() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE aid bigint; state text; selected_count bigint;
BEGIN
 IF TG_TABLE_NAME='asignacion_radio' THEN aid=NEW.id;
 ELSIF TG_OP='DELETE' THEN aid=OLD.asignacion_id;
 ELSE aid=NEW.asignacion_id; END IF;
 SELECT estado INTO state FROM territory.asignacion_radio WHERE id=aid;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT count(*) INTO selected_count FROM territory.candidato_asignacion WHERE asignacion_id=aid AND seleccionado;
 IF (state IN ('unique_provisional','verified') AND selected_count<>1)
 OR (state NOT IN ('unique_provisional','verified') AND selected_count<>0)
 THEN RAISE EXCEPTION 'assignment_state_selection_mismatch'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER assignment_result_consistent AFTER INSERT OR UPDATE ON territory.asignacion_radio
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION territory.check_assignment_result();
CREATE CONSTRAINT TRIGGER candidate_result_consistent AFTER INSERT OR UPDATE OR DELETE ON territory.candidato_asignacion
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION territory.check_assignment_result();

ALTER TABLE analytics.contexto_radio ADD COLUMN disponible_desde timestamptz;

CREATE VIEW analytics.registros_fuente_semana AS
 SELECT e.id ejecucion_id,l.archivo_id,w.inicio semana_inicio,
 count(*) registros_fuente,
 count(*) FILTER(WHERE ex.motivos IS NULL) registros_incluidos_en_conteos,
 count(*) FILTER(WHERE ex.motivos IS NOT NULL) registros_excluidos_o_pendientes,
 count(*) FILTER(WHERE ref.valor IS NULL) sin_fecha_referencia
 FROM analytics.ejecucion e JOIN analytics.fuente_ejecucion fe ON fe.ejecucion_id=e.id
 JOIN ingestion.lote_importacion l ON l.id=fe.lote_id
 JOIN ingestion.fila_staging s ON s.lote_id=l.id
 JOIN epidemiology.registro_epidemiologico r ON r.fila_id=s.id
 LEFT JOIN LATERAL (SELECT f.valor FROM epidemiology.fecha_registro f JOIN epidemiology.prioridad_fecha p ON p.tipo_id=f.tipo_id
  WHERE f.registro_id=r.id AND f.estado='valid' AND p.politica_id=e.politica_temporal_id ORDER BY p.prioridad LIMIT 1) ref ON true
 LEFT JOIN analytics.semana_epidemiologica w ON ref.valor BETWEEN w.inicio AND w.fin AND w.calendario_version=e.calendario_version
 LEFT JOIN LATERAL (SELECT string_agg(motivo,',') motivos FROM analytics.exclusion_registro x WHERE x.ejecucion_id=e.id AND x.registro_id=r.id) ex ON true
 GROUP BY e.id,l.archivo_id,w.inicio;

CREATE VIEW analytics.candidatos_espaciales_pendientes AS
 SELECT a.id asignacion_id,g.registro_id,r.codigo radio_candidato,a.estado,g.requiere_revision,
 false AS asignacion_aprobada,false AS etiqueta_ml_usable
 FROM territory.asignacion_radio a JOIN territory.geocodificacion g ON g.id=a.geocodificacion_id
 JOIN territory.candidato_asignacion c ON c.asignacion_id=a.id
 JOIN territory.radio_censal r ON r.id=c.radio_id
 WHERE NOT c.seleccionado;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA epidemiology,territory FROM PUBLIC;
GRANT SELECT ON analytics.registros_fuente_semana,analytics.candidatos_espaciales_pendientes TO sigard_epi_importer,sigard_epi_analytics_reader;
