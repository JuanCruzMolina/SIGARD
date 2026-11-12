-- Logical rollback for existing SISA batches; source rows remain immutable evidence.
CREATE TABLE ingestion.estado_lote_sisa (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 lote_id bigint NOT NULL REFERENCES ingestion.lote_importacion,
 estado text NOT NULL CHECK(estado IN ('accepted','withdrawn')),
 motivo text NOT NULL CHECK(motivo<>''), creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER sisa_batch_state_immutable BEFORE UPDATE OR DELETE ON ingestion.estado_lote_sisa
 FOR EACH ROW EXECUTE FUNCTION epidemiology.review_is_immutable();
CREATE VIEW ingestion.lotes_sisa_vigentes AS
 SELECT b.* FROM ingestion.lote_importacion b
 LEFT JOIN LATERAL(SELECT estado FROM ingestion.estado_lote_sisa s WHERE s.lote_id=b.id ORDER BY s.id DESC LIMIT 1) s ON true
 WHERE b.estado='complete' AND coalesce(s.estado,'accepted')='accepted';
CREATE VIEW analytics.disponibilidad_dataset_predictivo AS
 SELECT d.version,
 NOT EXISTS(SELECT 1 FROM analytics.fuente_dataset_predictivo f
   WHERE f.dataset_version=d.version AND NOT EXISTS(SELECT 1 FROM ingestion.lotes_sisa_vigentes b WHERE b.id=f.lote_id))
 AND NOT EXISTS(SELECT 1 FROM analytics.complemento_dataset_predictivo f
   WHERE f.dataset_version=d.version AND NOT EXISTS(SELECT 1 FROM ingestion.lotes_complementarios_vigentes b WHERE b.id=f.lote_id))
 AS lotes_vigentes FROM analytics.dataset_predictivo d;
REVOKE ALL ON ingestion.estado_lote_sisa,ingestion.lotes_sisa_vigentes,analytics.disponibilidad_dataset_predictivo FROM PUBLIC;
GRANT SELECT,INSERT ON ingestion.estado_lote_sisa TO sigard_epi_importer;
GRANT USAGE,SELECT ON SEQUENCE ingestion.estado_lote_sisa_id_seq TO sigard_epi_importer;
GRANT SELECT ON ingestion.lotes_sisa_vigentes TO sigard_epi_importer;
GRANT SELECT ON analytics.disponibilidad_dataset_predictivo TO sigard_epi_importer,sigard_epi_analytics_reader;
