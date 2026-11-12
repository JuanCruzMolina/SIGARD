-- Additive private predictive core; existing source/ML artifacts are untouched.
CREATE TABLE ingestion.lote_complementario (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 archivo_id bigint NOT NULL REFERENCES ingestion.archivo_fuente,
 adaptador text NOT NULL, version text NOT NULL, tipo text NOT NULL
 CHECK(tipo IN ('climate_daily','public_aggregate','census_aggregate')),
 filas_fuente integer NOT NULL CHECK(filas_fuente>=0),
 filas_aceptadas integer NOT NULL CHECK(filas_aceptadas>=0 AND filas_aceptadas<=filas_fuente),
 contrato jsonb NOT NULL, creado_en timestamptz NOT NULL DEFAULT now(),
 UNIQUE(archivo_id,adaptador,version)
);
CREATE TABLE ingestion.estado_lote_complementario (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 lote_id bigint NOT NULL REFERENCES ingestion.lote_complementario,
 estado text NOT NULL CHECK(estado IN ('accepted','withdrawn')),
 motivo text NOT NULL CHECK(motivo<>''), creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ingestion.error_complementario (
 lote_id bigint REFERENCES ingestion.lote_complementario, fila integer NOT NULL,
 codigo text NOT NULL, PRIMARY KEY(lote_id,fila,codigo)
);
CREATE VIEW ingestion.lotes_complementarios_vigentes AS
 SELECT b.* FROM ingestion.lote_complementario b
 JOIN LATERAL(SELECT estado FROM ingestion.estado_lote_complementario s
 WHERE s.lote_id=b.id ORDER BY s.id DESC LIMIT 1) s ON s.estado='accepted';

CREATE TABLE territory.estacion_climatica (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, codigo text NOT NULL UNIQUE,
 descripcion text NOT NULL, geom geometry(Point,4326) NOT NULL,
 zona_horaria text NOT NULL, CHECK(ST_IsValid(geom))
);
CREATE TABLE epidemiology.clima_diario (
 lote_id bigint REFERENCES ingestion.lote_complementario,
 estacion_id bigint REFERENCES territory.estacion_climatica, fecha date NOT NULL,
 temperatura_min double precision NOT NULL, temperatura_max double precision NOT NULL,
 temperatura_media double precision NOT NULL, humedad_media double precision NOT NULL CHECK(humedad_media BETWEEN 0 AND 100),
 precipitacion double precision NOT NULL CHECK(precipitacion>=0),
 disponible_desde timestamptz, PRIMARY KEY(lote_id,estacion_id,fecha),
 CHECK(temperatura_min<=temperatura_media AND temperatura_media<=temperatura_max)
);
CREATE TABLE epidemiology.evento_agregado (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, codigo text NOT NULL UNIQUE
);
CREATE TABLE epidemiology.agregado_publico (
 lote_id bigint REFERENCES ingestion.lote_complementario,
 departamento_id bigint REFERENCES territory.departamento,
 semana_id bigint REFERENCES analytics.semana_epidemiologica,
 evento_id bigint REFERENCES epidemiology.evento_agregado,
 grupo_etario_id bigint REFERENCES epidemiology.grupo_etario,
 cantidad integer NOT NULL CHECK(cantidad>=0),
 PRIMARY KEY(lote_id,departamento_id,semana_id,evento_id,grupo_etario_id)
);
CREATE TABLE territory.variable_censal (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, codigo text NOT NULL UNIQUE
);
CREATE TABLE territory.categoria_censal (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 variable_id bigint NOT NULL REFERENCES territory.variable_censal,
 codigo text NOT NULL, descripcion text NOT NULL, UNIQUE(variable_id,codigo)
);
CREATE TABLE territory.observacion_censal (
 lote_id bigint REFERENCES ingestion.lote_complementario,
 radio_id bigint REFERENCES territory.radio_censal,
 categoria_id bigint REFERENCES territory.categoria_censal,
 cantidad integer NOT NULL CHECK(cantidad>=0), PRIMARY KEY(lote_id,radio_id,categoria_id)
);

CREATE TABLE analytics.dataset_predictivo (
 version text PRIMARY KEY, contrato jsonb NOT NULL,
 entrada_sha256 char(64) NOT NULL, calendario_version text NOT NULL,
 resolucion_version text NOT NULL REFERENCES epidemiology.version_resolucion,
 unidad_espacial text NOT NULL CHECK(unidad_espacial='capital_source_residence'),
 creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE analytics.fuente_dataset_predictivo (
 dataset_version text REFERENCES analytics.dataset_predictivo,
 lote_id bigint REFERENCES ingestion.lote_importacion, PRIMARY KEY(dataset_version,lote_id)
);
CREATE TABLE analytics.complemento_dataset_predictivo (
 dataset_version text REFERENCES analytics.dataset_predictivo,
 lote_id bigint REFERENCES ingestion.lote_complementario, PRIMARY KEY(dataset_version,lote_id)
);
CREATE TABLE analytics.seleccion_registro_predictivo (
 dataset_version text REFERENCES analytics.dataset_predictivo,
 registro_id bigint REFERENCES epidemiology.registro_epidemiologico,
 motivo text NOT NULL, incluido boolean NOT NULL, PRIMARY KEY(dataset_version,registro_id)
);
CREATE TABLE analytics.serie_predictiva (
 dataset_version text REFERENCES analytics.dataset_predictivo,
 semana_id bigint REFERENCES analytics.semana_epidemiologica,
 unidad_codigo text NOT NULL, registros_observados integer NOT NULL CHECK(registros_observados>=0),
 conteo_conservador integer CHECK(conteo_conservador>=0),
 conteo_experimental integer CHECK(conteo_experimental>=0),
 cobertura text NOT NULL CHECK(cobertura IN ('experimental_assumed','unknown','out_of_scope')),
 fechas_muestra integer NOT NULL CHECK(fechas_muestra>=0),
 pendientes_fecha integer NOT NULL CHECK(pendientes_fecha>=0),
 disponible_desde timestamptz, disponibilidad_verificada boolean NOT NULL DEFAULT false,
 PRIMARY KEY(dataset_version,semana_id,unidad_codigo),
 CHECK(conteo_conservador IS NULL),
 CHECK(conteo_experimental IS NULL OR cobertura='experimental_assumed'),
 CHECK(NOT disponibilidad_verificada OR disponible_desde IS NOT NULL)
);
CREATE TABLE analytics.clima_predictivo (
 dataset_version text REFERENCES analytics.dataset_predictivo,
 semana_id bigint REFERENCES analytics.semana_epidemiologica,
 temperatura double precision, humedad double precision, precipitacion double precision,
 dias integer NOT NULL CHECK(dias BETWEEN 0 AND 7), disponible_desde timestamptz,
 PRIMARY KEY(dataset_version,semana_id),
 CHECK(dias=7 OR (temperatura IS NULL AND humedad IS NULL AND precipitacion IS NULL))
);
CREATE TABLE analytics.modelo_predictivo (
 version text PRIMARY KEY, componente text NOT NULL CHECK(componente='principal'),
 dataset_version text NOT NULL REFERENCES analytics.dataset_predictivo,
 estado text NOT NULL CHECK(estado IN ('candidate_failed','candidate_retrospective','active')),
 artefacto bytea NOT NULL, artefacto_sha256 char(64) NOT NULL,
 protocolo jsonb NOT NULL, metadatos jsonb NOT NULL, metricas jsonb NOT NULL,
 creado_en timestamptz NOT NULL DEFAULT now(), CHECK(estado<>'active')
);
CREATE UNIQUE INDEX un_solo_candidato_predictivo ON analytics.modelo_predictivo(componente);
CREATE TABLE analytics.prediccion_predictiva (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, modelo_version text REFERENCES analytics.modelo_predictivo,
 origen date NOT NULL, modo text NOT NULL CHECK(modo IN ('retrospective','operational')),
 resultado jsonb NOT NULL, creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE VIEW analytics.serie_predictiva_lectura AS
 SELECT s.*,w.inicio,w.fin,w.anio,w.numero,w.semanas_anio,d.entrada_sha256,d.calendario_version,
 d.unidad_espacial FROM analytics.serie_predictiva s JOIN analytics.dataset_predictivo d ON d.version=s.dataset_version
 JOIN analytics.semana_epidemiologica w ON w.id=s.semana_id;

-- No importer can mutate accepted evidence; withdrawal is an append-only event.
DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['ingestion.lote_complementario','ingestion.estado_lote_complementario',
 'epidemiology.clima_diario','epidemiology.agregado_publico','territory.observacion_censal',
 'analytics.dataset_predictivo','analytics.fuente_dataset_predictivo','analytics.complemento_dataset_predictivo',
 'analytics.seleccion_registro_predictivo','analytics.serie_predictiva','analytics.clima_predictivo',
 'analytics.modelo_predictivo','analytics.prediccion_predictiva'] LOOP
 EXECUTE format('CREATE TRIGGER predictive_immutable BEFORE UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION epidemiology.review_is_immutable()',item);
 END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA ingestion,epidemiology,territory,analytics FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA ingestion,epidemiology,territory,analytics FROM PUBLIC;
GRANT SELECT,INSERT ON ingestion.lote_complementario,ingestion.estado_lote_complementario,ingestion.error_complementario,
 territory.estacion_climatica,epidemiology.clima_diario,epidemiology.evento_agregado,epidemiology.agregado_publico,
 territory.variable_censal,territory.categoria_censal,territory.observacion_censal,
 analytics.dataset_predictivo,analytics.fuente_dataset_predictivo,analytics.complemento_dataset_predictivo,
 analytics.seleccion_registro_predictivo,analytics.serie_predictiva,analytics.clima_predictivo,
 analytics.modelo_predictivo,analytics.prediccion_predictiva TO sigard_epi_importer;
GRANT SELECT ON ingestion.lotes_complementarios_vigentes TO sigard_epi_importer;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA ingestion,epidemiology,territory,analytics TO sigard_epi_importer;
GRANT SELECT ON analytics.dataset_predictivo,analytics.serie_predictiva_lectura,
 analytics.serie_predictiva,analytics.clima_predictivo TO sigard_epi_analytics_reader;
-- The reader receives serialized estimator metadata only, never patient IDs.
GRANT SELECT ON analytics.modelo_predictivo TO sigard_epi_analytics_reader;
GRANT INSERT,SELECT ON analytics.prediccion_predictiva TO sigard_epi_analytics_reader;
GRANT USAGE,SELECT ON SEQUENCE analytics.prediccion_predictiva_id_seq TO sigard_epi_analytics_reader;
