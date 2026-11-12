CREATE TABLE ingestion.intento_complementario (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, fuente_sha256 char(64) NOT NULL,
 adaptador text NOT NULL, version text NOT NULL,
 estado text NOT NULL CHECK(estado IN ('imported','already_imported','failed')),
 codigo text NOT NULL, creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ingestion.fila_complementaria (
 lote_id bigint REFERENCES ingestion.lote_complementario, ordinal integer NOT NULL CHECK(ordinal>0),
 contenido jsonb NOT NULL CHECK(jsonb_typeof(contenido)='object'),
 sha256 char(64) NOT NULL, PRIMARY KEY(lote_id,ordinal)
);
CREATE TRIGGER complementary_staging_immutable BEFORE UPDATE OR DELETE ON ingestion.fila_complementaria
 FOR EACH ROW EXECUTE FUNCTION epidemiology.review_is_immutable();
CREATE TRIGGER complementary_attempt_immutable BEFORE UPDATE OR DELETE ON ingestion.intento_complementario
 FOR EACH ROW EXECUTE FUNCTION epidemiology.review_is_immutable();
REVOKE ALL ON ingestion.intento_complementario,ingestion.fila_complementaria FROM PUBLIC;
GRANT INSERT,SELECT ON ingestion.intento_complementario,ingestion.fila_complementaria TO sigard_epi_importer;
GRANT USAGE,SELECT ON SEQUENCE ingestion.intento_complementario_id_seq TO sigard_epi_importer;
