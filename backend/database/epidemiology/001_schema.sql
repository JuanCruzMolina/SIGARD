-- Private operational 3NF schemas. No changes to public API entities.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS ingestion;
CREATE SCHEMA epidemiology;
CREATE SCHEMA territory;
CREATE SCHEMA analytics;
REVOKE ALL ON SCHEMA ingestion,epidemiology,territory,analytics FROM PUBLIC;

CREATE TABLE ingestion.archivo_fuente (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 nombre_original text NOT NULL, sha256 char(64) NOT NULL UNIQUE CHECK(sha256 ~ '^[a-f0-9]{64}$'),
 bytes bigint NOT NULL CHECK(bytes>=0), periodo_declarado text,
 fecha_extraccion date, procedencia text NOT NULL, entrega_version text NOT NULL,
 contenido_original bytea NOT NULL CHECK(octet_length(contenido_original)=bytes)
);
CREATE TABLE ingestion.hoja_fuente (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 archivo_id bigint NOT NULL REFERENCES ingestion.archivo_fuente,
 ordinal integer NOT NULL CHECK(ordinal>0), nombre text NOT NULL,
 fila_encabezado integer NOT NULL CHECK(fila_encabezado>=0), layout_sha256 char(64), preambulo jsonb NOT NULL DEFAULT '[]',
 UNIQUE(archivo_id,ordinal), UNIQUE(archivo_id,nombre)
);
CREATE TABLE ingestion.columna_fuente (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, hoja_id bigint NOT NULL REFERENCES ingestion.hoja_fuente,
 ordinal integer NOT NULL CHECK(ordinal>0), nombre_original text, campo_propuesto text,
 UNIQUE(hoja_id,ordinal)
);
CREATE TABLE ingestion.lote_importacion (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, archivo_id bigint NOT NULL REFERENCES ingestion.archivo_fuente,
 importador_version text NOT NULL, creado_en timestamptz NOT NULL DEFAULT now(),
 estado text NOT NULL CHECK(estado IN ('loading','complete')),
 filas_leidas integer NOT NULL DEFAULT 0 CHECK(filas_leidas>=0),
 filas_normalizadas integer NOT NULL DEFAULT 0 CHECK(filas_normalizadas>=0),
 filas_parciales integer NOT NULL DEFAULT 0 CHECK(filas_parciales>=0),
 validacion jsonb NOT NULL DEFAULT '{}', UNIQUE(archivo_id,importador_version)
);
CREATE TABLE ingestion.fila_staging (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 lote_id bigint NOT NULL REFERENCES ingestion.lote_importacion,
 hoja_id bigint NOT NULL REFERENCES ingestion.hoja_fuente,
 numero_fila integer NOT NULL CHECK(numero_fila>0), contenido jsonb NOT NULL CHECK(jsonb_typeof(contenido)='array'),
 sha256 char(64) NOT NULL CHECK(sha256 ~ '^[a-f0-9]{64}$'),
 estado text NOT NULL CHECK(estado IN ('normalized','partial')),
 UNIQUE(lote_id,hoja_id,numero_fila)
);
CREATE INDEX ix_staging_hash ON ingestion.fila_staging(sha256);
CREATE FUNCTION ingestion.check_sheet_batch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (SELECT archivo_id FROM ingestion.hoja_fuente WHERE id=NEW.hoja_id)
    IS DISTINCT FROM (SELECT archivo_id FROM ingestion.lote_importacion WHERE id=NEW.lote_id)
 THEN RAISE EXCEPTION 'sheet_batch_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER sheet_batch_consistent BEFORE INSERT OR UPDATE ON ingestion.fila_staging
 FOR EACH ROW EXECUTE FUNCTION ingestion.check_sheet_batch();

CREATE TABLE territory.pais (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, nombre text NOT NULL UNIQUE, codigo text UNIQUE
);
CREATE TABLE territory.provincia (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, pais_id bigint NOT NULL REFERENCES territory.pais,
 nombre text NOT NULL, codigo text, UNIQUE(pais_id,nombre), UNIQUE(pais_id,codigo)
);
CREATE TABLE territory.departamento (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, provincia_id bigint NOT NULL REFERENCES territory.provincia,
 nombre text NOT NULL, codigo text, UNIQUE(provincia_id,nombre), UNIQUE(provincia_id,codigo)
);
CREATE TABLE territory.localidad (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, departamento_id bigint NOT NULL REFERENCES territory.departamento,
 nombre text NOT NULL, codigo text, UNIQUE(departamento_id,nombre), UNIQUE(departamento_id,codigo)
);
CREATE TABLE territory.version_geometria (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version text NOT NULL UNIQUE,
 fuente_sha256 char(64) NOT NULL, crs text NOT NULL CHECK(crs='EPSG:4326')
);
CREATE TABLE territory.fraccion_censal (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, departamento_id bigint NOT NULL REFERENCES territory.departamento,
 codigo text NOT NULL CHECK(codigo<>''), UNIQUE(departamento_id,codigo)
);
CREATE TABLE territory.radio_censal (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, fraccion_id bigint NOT NULL REFERENCES territory.fraccion_censal,
 version_geometria_id bigint NOT NULL REFERENCES territory.version_geometria,
 codigo text NOT NULL CHECK(codigo<>''), geom geometry(MultiPolygon,4326) NOT NULL,
 UNIQUE(version_geometria_id,codigo), CHECK(ST_IsValid(geom)), CHECK(NOT ST_IsEmpty(geom))
);
CREATE INDEX ix_radio_geom ON territory.radio_censal USING gist(geom);
CREATE TABLE territory.universo (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version text NOT NULL UNIQUE, descripcion text NOT NULL
);
CREATE TABLE territory.miembro_universo (
 universo_id bigint REFERENCES territory.universo, radio_id bigint REFERENCES territory.radio_censal,
 PRIMARY KEY(universo_id,radio_id)
);
CREATE TABLE territory.contexto_censal (
 radio_id bigint REFERENCES territory.radio_censal, version text NOT NULL,
 poblacion integer NOT NULL CHECK(poblacion>=0), fuente_sha256 char(64) NOT NULL,
 PRIMARY KEY(radio_id,version)
);
CREATE TABLE territory.vecindad (
 radio_id bigint REFERENCES territory.radio_censal, vecino_id bigint REFERENCES territory.radio_censal,
 regla_version text NOT NULL, PRIMARY KEY(radio_id,vecino_id,regla_version), CHECK(radio_id<>vecino_id)
);
CREATE TABLE territory.domicilio (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, localidad_id bigint REFERENCES territory.localidad,
 calle_original text, numero_original text
);
CREATE TABLE territory.normalizacion_domicilio (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, domicilio_id bigint NOT NULL REFERENCES territory.domicilio,
 version text NOT NULL, direccion_normalizada text, calle_oficial text, calle_codigo text,
 estado text NOT NULL, UNIQUE(domicilio_id,version)
);
CREATE TABLE territory.proceso_geocodificacion (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, proveedor text NOT NULL, metodo text NOT NULL,
 version text NOT NULL, UNIQUE(proveedor,metodo,version)
);

CREATE TABLE epidemiology.grupo_etario (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, literal text NOT NULL UNIQUE
);
CREATE TABLE epidemiology.registro_epidemiologico (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, fila_id bigint NOT NULL UNIQUE REFERENCES ingestion.fila_staging,
 identificador_externo text, grupo_etario_id bigint REFERENCES epidemiology.grupo_etario,
 domicilio_id bigint REFERENCES territory.domicilio,
 estado_normalizacion text NOT NULL CHECK(estado_normalizacion IN ('complete','partial')),
 disponible_desde timestamptz
);
CREATE INDEX ix_registro_evento ON epidemiology.registro_epidemiologico(identificador_externo);
CREATE TABLE epidemiology.incidencia_validacion (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, registro_id bigint NOT NULL REFERENCES epidemiology.registro_epidemiologico,
 codigo text NOT NULL, columna_id bigint REFERENCES ingestion.columna_fuente,
 UNIQUE NULLS NOT DISTINCT(registro_id,codigo,columna_id)
);
CREATE TABLE epidemiology.relacion_registro (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, registro_id bigint NOT NULL REFERENCES epidemiology.registro_epidemiologico,
 otro_id bigint NOT NULL REFERENCES epidemiology.registro_epidemiologico,
 tipo text NOT NULL CHECK(tipo IN ('exact_duplicate','possible_revision','same_external_id')),
 evidencia text NOT NULL, revision_estado text NOT NULL CHECK(revision_estado IN ('technical_exact','pending','accepted','rejected')),
 UNIQUE(registro_id,otro_id,tipo), CHECK(registro_id<>otro_id)
);
CREATE TABLE epidemiology.catalogo_clasificacion (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, codigo text NOT NULL UNIQUE
);
CREATE TABLE epidemiology.clasificacion_registro (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, registro_id bigint NOT NULL REFERENCES epidemiology.registro_epidemiologico,
 columna_id bigint NOT NULL REFERENCES ingestion.columna_fuente, valor_literal text NOT NULL,
 fecha_revision date, UNIQUE(registro_id,columna_id)
);
CREATE TABLE epidemiology.regla_normalizacion_clasificacion (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version text NOT NULL,
 literal_canonico text NOT NULL, catalogo_id bigint NOT NULL REFERENCES epidemiology.catalogo_clasificacion,
 estado_validacion text NOT NULL CHECK(estado_validacion IN ('provisional','validated')),
 UNIQUE(version,literal_canonico)
);
CREATE TABLE epidemiology.normalizacion_clasificacion (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, observacion_id bigint NOT NULL REFERENCES epidemiology.clasificacion_registro,
 regla_id bigint NOT NULL REFERENCES epidemiology.regla_normalizacion_clasificacion,
 aplicada_en timestamptz NOT NULL DEFAULT now(), UNIQUE(observacion_id,regla_id)
);
CREATE TABLE epidemiology.tipo_fecha (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, codigo text NOT NULL UNIQUE
);
CREATE TABLE epidemiology.fecha_registro (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, registro_id bigint NOT NULL REFERENCES epidemiology.registro_epidemiologico,
 tipo_id bigint NOT NULL REFERENCES epidemiology.tipo_fecha,
 columna_id bigint NOT NULL REFERENCES ingestion.columna_fuente,
 valor date, estado text NOT NULL CHECK(estado IN ('valid','missing','invalid_format','out_of_range')),
 parser_version text NOT NULL, UNIQUE(registro_id,columna_id,parser_version),
 CHECK((estado='valid')=(valor IS NOT NULL))
);
CREATE INDEX ix_fecha_valor ON epidemiology.fecha_registro(valor,tipo_id);
CREATE TABLE epidemiology.politica_temporal (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version text NOT NULL UNIQUE, descripcion text NOT NULL
);
CREATE TABLE epidemiology.prioridad_fecha (
 politica_id bigint REFERENCES epidemiology.politica_temporal, tipo_id bigint REFERENCES epidemiology.tipo_fecha,
 prioridad integer NOT NULL CHECK(prioridad>0), PRIMARY KEY(politica_id,tipo_id), UNIQUE(politica_id,prioridad)
);
CREATE TABLE epidemiology.politica_clasificacion (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version text NOT NULL UNIQUE, definicion text NOT NULL
);
CREATE TABLE epidemiology.clase_admitida (
 politica_id bigint REFERENCES epidemiology.politica_clasificacion, catalogo_id bigint REFERENCES epidemiology.catalogo_clasificacion,
 PRIMARY KEY(politica_id,catalogo_id)
);
CREATE TABLE territory.geocodificacion (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, registro_id bigint NOT NULL REFERENCES epidemiology.registro_epidemiologico,
 proceso_id bigint NOT NULL REFERENCES territory.proceso_geocodificacion, geom geometry(Point,4326),
 estado text NOT NULL, precision_literal text, confianza text, requiere_revision boolean NOT NULL,
 crs_estado text NOT NULL CHECK(crs_estado IN ('declared','assumed','verified')),
 radio_declarado text, fraccion_declarada text, UNIQUE(registro_id,proceso_id),
 CHECK(geom IS NULL OR (ST_X(geom) BETWEEN -180 AND 180 AND ST_Y(geom) BETWEEN -90 AND 90))
);
CREATE INDEX ix_geocod_geom ON territory.geocodificacion USING gist(geom);
CREATE TABLE territory.asignacion_radio (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, geocodificacion_id bigint NOT NULL REFERENCES territory.geocodificacion,
 version_geometria_id bigint NOT NULL REFERENCES territory.version_geometria,
 estado text NOT NULL CHECK(estado IN
 ('unique_provisional','verified','ambiguous','boundary','outside','invalid','insufficient')),
 evidencia text NOT NULL, UNIQUE(geocodificacion_id,version_geometria_id)
);
CREATE TABLE territory.candidato_asignacion (
 asignacion_id bigint REFERENCES territory.asignacion_radio, radio_id bigint REFERENCES territory.radio_censal,
 predicado text NOT NULL, seleccionado boolean NOT NULL DEFAULT false, PRIMARY KEY(asignacion_id,radio_id)
);
CREATE UNIQUE INDEX uq_candidate_selected ON territory.candidato_asignacion(asignacion_id) WHERE seleccionado;
CREATE FUNCTION territory.check_candidate_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (SELECT version_geometria_id FROM territory.radio_censal WHERE id=NEW.radio_id)
 IS DISTINCT FROM (SELECT version_geometria_id FROM territory.asignacion_radio WHERE id=NEW.asignacion_id)
 THEN RAISE EXCEPTION 'candidate_geometry_version_mismatch'; END IF;
 IF NEW.seleccionado AND (SELECT estado FROM territory.asignacion_radio WHERE id=NEW.asignacion_id) NOT IN ('unique_provisional','verified')
 THEN RAISE EXCEPTION 'ambiguous_candidate_cannot_be_selected'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER candidate_consistent BEFORE INSERT OR UPDATE ON territory.candidato_asignacion
 FOR EACH ROW EXECUTE FUNCTION territory.check_candidate_version();
CREATE TABLE epidemiology.criterio_cobertura (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version text NOT NULL UNIQUE,
 politica_clasificacion_id bigint NOT NULL REFERENCES epidemiology.politica_clasificacion,
 definicion_poblacion text NOT NULL, filtro_extraccion text NOT NULL
);
CREATE TABLE epidemiology.cobertura_fuente (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, archivo_id bigint NOT NULL REFERENCES ingestion.archivo_fuente,
 universo_id bigint NOT NULL REFERENCES territory.universo, criterio_id bigint NOT NULL REFERENCES epidemiology.criterio_cobertura,
 inicio date NOT NULL, fin date NOT NULL, CHECK(inicio<=fin),
 UNIQUE(archivo_id,universo_id,criterio_id,inicio,fin)
);
CREATE TABLE epidemiology.revision_cobertura (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, cobertura_id bigint NOT NULL REFERENCES epidemiology.cobertura_fuente,
 estado text NOT NULL CHECK(estado IN ('verified','experimental_assumed','unknown','out_of_scope')),
 evidencia text NOT NULL CHECK(evidencia<>''), responsable text NOT NULL,
 revisada_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_cobertura_intervalo ON epidemiology.cobertura_fuente(universo_id,inicio,fin);

-- Analytics: explicitly reproducible, controlled denormalization.
CREATE TABLE analytics.semana_epidemiologica (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, calendario_version text NOT NULL,
 anio integer NOT NULL, numero integer NOT NULL CHECK(numero BETWEEN 1 AND 53),
 inicio date NOT NULL, fin date NOT NULL CHECK(fin=inicio+6),
 semanas_anio integer NOT NULL CHECK(semanas_anio IN (52,53)),
 UNIQUE(calendario_version,anio,numero), UNIQUE(calendario_version,inicio)
);
CREATE TABLE analytics.ejecucion (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, version text NOT NULL UNIQUE,
 universo_id bigint NOT NULL REFERENCES territory.universo,
 politica_temporal_id bigint NOT NULL REFERENCES epidemiology.politica_temporal,
 politica_clasificacion_id bigint NOT NULL REFERENCES epidemiology.politica_clasificacion,
 criterio_cobertura_id bigint NOT NULL REFERENCES epidemiology.criterio_cobertura,
 inicio date NOT NULL, fin date NOT NULL CHECK(inicio<=fin), calendario_version text NOT NULL,
 escenario text NOT NULL CHECK(escenario IN ('conservative','experimental_assumed')),
 aceptar_geografia_provisional boolean NOT NULL DEFAULT false,
 corte_informacion timestamptz NOT NULL, modo text NOT NULL CHECK(modo IN ('retrospective','as_of')),
 clima_version text,
 equivalencia_ml_verificada boolean NOT NULL DEFAULT false,
 creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE analytics.fuente_ejecucion (
 ejecucion_id bigint REFERENCES analytics.ejecucion, lote_id bigint REFERENCES ingestion.lote_importacion,
 PRIMARY KEY(ejecucion_id,lote_id)
);
CREATE TABLE analytics.contexto_radio (
 universo_id bigint REFERENCES territory.universo, radio_id bigint REFERENCES territory.radio_censal,
 superficie_km2 double precision NOT NULL CHECK(superficie_km2>0), poblacion integer NOT NULL CHECK(poblacion>=0),
 cantidad_vecinos integer NOT NULL CHECK(cantidad_vecinos>=0), fuente_sha256 char(64) NOT NULL,
 PRIMARY KEY(universo_id,radio_id), FOREIGN KEY(universo_id,radio_id) REFERENCES territory.miembro_universo
);
CREATE TABLE analytics.conteos_radio_semana (
 ejecucion_id bigint REFERENCES analytics.ejecucion, radio_id bigint REFERENCES territory.radio_censal,
 semana_id bigint REFERENCES analytics.semana_epidemiologica,
 registros_observados integer NOT NULL CHECK(registros_observados>=0),
 cantidad_registros integer CHECK(cantidad_registros>=0), episodios_acreditados integer,
 presencia integer CHECK(presencia IN (0,1)), pendientes_posibles integer NOT NULL CHECK(pendientes_posibles>=0),
 fechas_aproximadas integer NOT NULL CHECK(fechas_aproximadas>=0),
 cobertura_estado text NOT NULL CHECK(cobertura_estado IN ('verified','experimental_assumed','unknown','out_of_scope')),
 estado_asignacion text NOT NULL, ultimo_disponible timestamptz, disponibilidad_verificada boolean NOT NULL DEFAULT false,
 PRIMARY KEY(ejecucion_id,radio_id,semana_id),
 CHECK(episodios_acreditados IS NULL),
 CHECK(cantidad_registros IS NULL OR (cobertura_estado IN ('verified','experimental_assumed') AND pendientes_posibles=0)),
 CHECK(cantidad_registros IS NULL OR presencia=(cantidad_registros>0)::integer)
);
CREATE INDEX ix_conteos_radio_semana ON analytics.conteos_radio_semana(radio_id,semana_id,ejecucion_id);
CREATE TABLE analytics.exclusion_registro (
 ejecucion_id bigint REFERENCES analytics.ejecucion, registro_id bigint REFERENCES epidemiology.registro_epidemiologico,
 motivo text NOT NULL, PRIMARY KEY(ejecucion_id,registro_id,motivo)
);
CREATE TABLE analytics.clima_semana (
 version text NOT NULL, semana_id bigint REFERENCES analytics.semana_epidemiologica,
 temperatura double precision, humedad double precision, precipitacion double precision,
 disponible_desde timestamptz, fuente_sha256 char(64) NOT NULL, compatible boolean NOT NULL,
 PRIMARY KEY(version,semana_id)
);

DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='sigard_epi_importer') THEN CREATE ROLE sigard_epi_importer NOLOGIN; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='sigard_epi_analytics_reader') THEN CREATE ROLE sigard_epi_analytics_reader NOLOGIN; END IF;
END $$;
GRANT USAGE ON SCHEMA ingestion,epidemiology,territory,analytics TO sigard_epi_importer;
GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA ingestion,epidemiology,territory,analytics TO sigard_epi_importer;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA ingestion,epidemiology,territory,analytics TO sigard_epi_importer;
GRANT USAGE ON SCHEMA analytics TO sigard_epi_analytics_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO sigard_epi_analytics_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA ingestion,epidemiology,territory,analytics FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA ingestion,epidemiology,territory,analytics FROM PUBLIC;
