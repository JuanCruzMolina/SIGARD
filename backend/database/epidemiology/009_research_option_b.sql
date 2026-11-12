-- New authorized research contracts; all earlier scenarios/models stay intact.
CREATE TABLE analytics.escenario_investigacion (
 version text PRIMARY KEY, calendario_version text NOT NULL,
 resolucion_version text NOT NULL REFERENCES epidemiology.version_resolucion,
 clima_lote_id bigint NOT NULL REFERENCES ingestion.lote_complementario,
 politica_ceros text NOT NULL CHECK(politica_ceros='option_b_complete_years_assumed_zero_v1'),
 contrato jsonb NOT NULL, protocolo jsonb NOT NULL, entrada_sha256 char(64) NOT NULL,
 creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE analytics.fuente_escenario_ml (
 escenario_version text REFERENCES analytics.escenario_investigacion,
 lote_id bigint REFERENCES ingestion.lote_importacion,
 PRIMARY KEY(escenario_version,lote_id)
);
CREATE TABLE analytics.registro_escenario_ml (
 escenario_version text REFERENCES analytics.escenario_investigacion,
 registro_id bigint REFERENCES epidemiology.registro_epidemiologico,
 lote_id bigint NOT NULL REFERENCES ingestion.lote_importacion,
 semana_id bigint REFERENCES analytics.semana_epidemiologica,
 elegible boolean NOT NULL, motivo text NOT NULL, tipo_fecha text,
 asignacion_id bigint REFERENCES territory.asignacion_radio,
 radio_id bigint REFERENCES territory.radio_censal,
 calidad_geografica text NOT NULL CHECK(calidad_geografica IN ('approximate','provisional','verified','unassigned')),
 PRIMARY KEY(escenario_version,registro_id),
 CHECK(NOT elegible OR semana_id IS NOT NULL),
 CHECK((radio_id IS NULL)=(calidad_geografica='unassigned'))
);
CREATE TABLE analytics.clima_escenario_ml (
 escenario_version text REFERENCES analytics.escenario_investigacion,
 semana_id bigint REFERENCES analytics.semana_epidemiologica,
 temperatura double precision, humedad double precision, precipitacion double precision,
 dias integer NOT NULL CHECK(dias BETWEEN 0 AND 7), disponible_desde timestamptz,
 PRIMARY KEY(escenario_version,semana_id),
 CHECK(dias=7 OR (temperatura IS NULL AND humedad IS NULL AND precipitacion IS NULL))
);
CREATE TABLE analytics.dataset_investigacion (
 version text PRIMARY KEY, escenario_version text NOT NULL REFERENCES analytics.escenario_investigacion,
 universo_id bigint NOT NULL REFERENCES territory.universo,
 politica_geografica text NOT NULL CHECK(politica_geografica IN ('approximate_included','provisional_verified')),
 contrato_sha256 char(64) NOT NULL, resumen jsonb NOT NULL,
 UNIQUE(escenario_version,universo_id,politica_geografica)
);
CREATE TABLE analytics.conteo_investigacion (
 dataset_version text REFERENCES analytics.dataset_investigacion,
 radio_id bigint REFERENCES territory.radio_censal,
 semana_id bigint REFERENCES analytics.semana_epidemiologica,
 cantidad integer NOT NULL CHECK(cantidad>=0), cero_asumido boolean NOT NULL,
 aproximados integer NOT NULL CHECK(aproximados>=0),
 provisionales integer NOT NULL CHECK(provisionales>=0),
 verificados integer NOT NULL CHECK(verificados>=0),
 PRIMARY KEY(dataset_version,radio_id,semana_id),
 CHECK(cero_asumido=(cantidad=0)),CHECK(cantidad=aproximados+provisionales+verificados)
);
CREATE INDEX ix_research_week ON analytics.conteo_investigacion(dataset_version,semana_id,radio_id);

CREATE TABLE analytics.modelo_investigacion (
 version text PRIMARY KEY, dataset_version text NOT NULL REFERENCES analytics.dataset_investigacion,
 familia text NOT NULL CHECK(familia IN ('A','B','V3')),
 horizonte integer NOT NULL CHECK(horizonte IN (1,2,4)),
 estado text NOT NULL CHECK(estado IN ('experimental_unvalidated','blocked')),
 ultimo_objetivo_ajuste date, metodo text,
 artefacto bytea, artefacto_sha256 char(64), protocolo_sha256 char(64) NOT NULL,
 metadatos jsonb NOT NULL, creado_en timestamptz NOT NULL DEFAULT now(),
 UNIQUE(dataset_version,familia,horizonte),
 CHECK(familia='V3' OR horizonte=1),
 CHECK((estado='blocked')=(artefacto IS NULL)),
 CHECK(estado='blocked' OR (artefacto_sha256 IS NOT NULL AND ultimo_objetivo_ajuste IS NOT NULL AND metodo IS NOT NULL))
);
CREATE TABLE analytics.evaluacion_investigacion (
 modelo_version text REFERENCES analytics.modelo_investigacion,
 particion text NOT NULL CHECK(particion IN ('development','holdout','sensitivity')),
 metricas jsonb NOT NULL, creado_en timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(modelo_version,particion)
);
CREATE TABLE analytics.prediccion_investigacion (
 modelo_version text REFERENCES analytics.modelo_investigacion,
 radio_id bigint REFERENCES territory.radio_censal, origen date NOT NULL,
 valor double precision NOT NULL CHECK(valor>=0 AND valor<'Infinity'::double precision),
 PRIMARY KEY(modelo_version,radio_id,origen)
);

CREATE FUNCTION analytics.check_research_record_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM epidemiology.registro_epidemiologico r
   JOIN ingestion.fila_staging f ON f.id=r.fila_id
   JOIN analytics.fuente_escenario_ml s ON s.escenario_version=NEW.escenario_version AND s.lote_id=f.lote_id
   WHERE r.id=NEW.registro_id AND f.lote_id=NEW.lote_id)
 THEN RAISE EXCEPTION 'research_record_source_mismatch'; END IF;
 IF NEW.asignacion_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM territory.asignacion_radio a
   JOIN territory.geocodificacion g ON g.id=a.geocodificacion_id
   WHERE a.id=NEW.asignacion_id AND g.registro_id=NEW.registro_id)
 THEN RAISE EXCEPTION 'research_assignment_record_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER research_record_source BEFORE INSERT ON analytics.registro_escenario_ml
 FOR EACH ROW EXECUTE FUNCTION analytics.check_research_record_source();

CREATE FUNCTION analytics.check_research_count() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM analytics.dataset_investigacion d
   JOIN territory.miembro_universo m ON m.universo_id=d.universo_id AND m.radio_id=NEW.radio_id
   JOIN analytics.escenario_investigacion s ON s.version=d.escenario_version
   JOIN analytics.semana_epidemiologica w ON w.id=NEW.semana_id AND w.calendario_version=s.calendario_version
   WHERE d.version=NEW.dataset_version AND (s.contrato->'scope'->'covered_weeks') ? w.inicio::text)
 THEN RAISE EXCEPTION 'research_count_universe_or_week_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER research_count_scope BEFORE INSERT ON analytics.conteo_investigacion
 FOR EACH ROW EXECUTE FUNCTION analytics.check_research_count();

CREATE FUNCTION analytics.check_research_prediction() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m analytics.modelo_investigacion%ROWTYPE;
BEGIN
 SELECT * INTO STRICT m FROM analytics.modelo_investigacion WHERE version=NEW.modelo_version;
 IF m.estado<>'experimental_unvalidated' OR m.ultimo_objetivo_ajuste>=NEW.origen
   OR (m.familia IN ('A','B') AND NEW.valor>1)
   OR NOT EXISTS(SELECT 1 FROM analytics.conteo_investigacion c
     JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
     WHERE c.dataset_version=m.dataset_version AND c.radio_id=NEW.radio_id AND w.inicio=NEW.origen)
   OR NOT EXISTS(SELECT 1 FROM analytics.conteo_investigacion c
     JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
     WHERE c.dataset_version=m.dataset_version AND c.radio_id=NEW.radio_id AND w.inicio=NEW.origen+7*m.horizonte)
 THEN RAISE EXCEPTION 'research_prediction_contract_or_origin_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER research_prediction_scope BEFORE INSERT ON analytics.prediccion_investigacion
 FOR EACH ROW EXECUTE FUNCTION analytics.check_research_prediction();
REVOKE ALL ON FUNCTION analytics.check_research_record_source(),analytics.check_research_count(),analytics.check_research_prediction() FROM PUBLIC;

CREATE VIEW analytics.disponibilidad_investigacion AS
 SELECT d.version,NOT EXISTS(SELECT 1 FROM analytics.fuente_escenario_ml f
   WHERE f.escenario_version=d.escenario_version AND NOT EXISTS(
     SELECT 1 FROM ingestion.lotes_sisa_vigentes b WHERE b.id=f.lote_id))
 AND EXISTS(SELECT 1 FROM analytics.escenario_investigacion s
   JOIN ingestion.lotes_complementarios_vigentes b ON b.id=s.clima_lote_id
   WHERE s.version=d.escenario_version) lotes_vigentes
 FROM analytics.dataset_investigacion d;

CREATE VIEW analytics.metadatos_investigacion AS
 SELECT d.*,u.version universe_version,s.calendario_version,s.politica_ceros,
 s.contrato,s.protocolo,s.entrada_sha256,s.creado_en,v.lotes_vigentes
 FROM analytics.dataset_investigacion d
 JOIN analytics.escenario_investigacion s ON s.version=d.escenario_version
 JOIN territory.universo u ON u.id=d.universo_id
 JOIN analytics.disponibilidad_investigacion v ON v.version=d.version;

CREATE VIEW analytics.base_investigacion AS
 SELECT d.version dataset_version,c.radio_id,r.codigo radio_censal,w.inicio fecha_inicio_semana,
 w.fin fin_origen,w.inicio+7 fecha_inicio_semana_objetivo,
 w.anio anio_epidemiologico,w.numero semana_epidemiologica,w.semanas_anio,
 c.cantidad count_origin,c.cero_asumido,c.aproximados,c.provisionales,c.verificados,
 x.superficie_km2,x.poblacion,x.poblacion/x.superficie_km2 densidad_poblacional,x.cantidad_vecinos,
 sin(2*pi()*(w.numero-1)/w.semanas_anio) estacionalidad_seno,
 cos(2*pi()*(w.numero-1)/w.semanas_anio) estacionalidad_coseno,
 d.universo_id,d.politica_geografica,s.version escenario_version,s.politica_ceros,
 s.calendario_version,gv.version version_territorial,x.fuente_sha256 contexto_sha256,target.cantidad target_count,
 CASE WHEN target.cantidad IS NOT NULL THEN (target.cantidad>0)::integer END objetivo_semana_siguiente
 FROM analytics.conteo_investigacion c
 JOIN analytics.dataset_investigacion d ON d.version=c.dataset_version
 JOIN analytics.escenario_investigacion s ON s.version=d.escenario_version
 JOIN territory.radio_censal r ON r.id=c.radio_id
 JOIN territory.version_geometria gv ON gv.id=r.version_geometria_id
 JOIN analytics.contexto_radio x ON x.universo_id=d.universo_id AND x.radio_id=c.radio_id
 JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
 LEFT JOIN analytics.semana_epidemiologica wt ON wt.inicio=w.inicio+7 AND wt.calendario_version=s.calendario_version
 LEFT JOIN analytics.conteo_investigacion target ON target.dataset_version=d.version
   AND target.radio_id=c.radio_id AND target.semana_id=wt.id;

CREATE VIEW analytics.vecindad_investigacion AS
 SELECT d.version dataset_version,a.codigo origen,b.codigo vecino
 FROM analytics.dataset_investigacion d
 JOIN territory.miembro_universo ma ON ma.universo_id=d.universo_id
 JOIN territory.vecindad n ON n.radio_id=ma.radio_id
 JOIN territory.miembro_universo mb ON mb.universo_id=d.universo_id AND mb.radio_id=n.vecino_id
 JOIN territory.radio_censal a ON a.id=n.radio_id JOIN territory.radio_censal b ON b.id=n.vecino_id;

CREATE VIEW analytics.investigacion_a AS
 SELECT dataset_version,radio_censal,fecha_inicio_semana,fin_origen,fecha_inicio_semana_objetivo,
 superficie_km2,poblacion,densidad_poblacional,cantidad_vecinos,semana_epidemiologica,
 estacionalidad_seno,estacionalidad_coseno,objetivo_semana_siguiente
 FROM analytics.base_investigacion;

CREATE VIEW analytics.investigacion_b AS
 SELECT a.*,(l1.cantidad>0)::integer local_presencia_exp_rezago_1,
 (l2.cantidad>0)::integer local_presencia_exp_rezago_2,
 (l3.cantidad>0)::integer local_presencia_exp_rezago_3,
 (l4.cantidad>0)::integer local_presencia_exp_rezago_4,
 (l1.cantidad IS NULL)::integer local_presencia_exp_rezago_1_missing,
 (l2.cantidad IS NULL)::integer local_presencia_exp_rezago_2_missing,
 (l3.cantidad IS NULL)::integer local_presencia_exp_rezago_3_missing,
 (l4.cantidad IS NULL)::integer local_presencia_exp_rezago_4_missing
 FROM analytics.investigacion_a a
 JOIN analytics.base_investigacion b ON b.dataset_version=a.dataset_version
   AND b.radio_censal=a.radio_censal AND b.fecha_inicio_semana=a.fecha_inicio_semana
 LEFT JOIN analytics.semana_epidemiologica w1 ON w1.inicio=a.fecha_inicio_semana-7 AND w1.calendario_version=b.calendario_version
 LEFT JOIN analytics.semana_epidemiologica w2 ON w2.inicio=a.fecha_inicio_semana-14 AND w2.calendario_version=b.calendario_version
 LEFT JOIN analytics.semana_epidemiologica w3 ON w3.inicio=a.fecha_inicio_semana-21 AND w3.calendario_version=b.calendario_version
 LEFT JOIN analytics.semana_epidemiologica w4 ON w4.inicio=a.fecha_inicio_semana-28 AND w4.calendario_version=b.calendario_version
 LEFT JOIN analytics.conteo_investigacion l1 ON l1.dataset_version=a.dataset_version AND l1.radio_id=b.radio_id AND l1.semana_id=w1.id
 LEFT JOIN analytics.conteo_investigacion l2 ON l2.dataset_version=a.dataset_version AND l2.radio_id=b.radio_id AND l2.semana_id=w2.id
 LEFT JOIN analytics.conteo_investigacion l3 ON l3.dataset_version=a.dataset_version AND l3.radio_id=b.radio_id AND l3.semana_id=w3.id
 LEFT JOIN analytics.conteo_investigacion l4 ON l4.dataset_version=a.dataset_version AND l4.radio_id=b.radio_id AND l4.semana_id=w4.id;

CREATE VIEW analytics.investigacion_v3 AS
 SELECT b.dataset_version,b.radio_censal radio_id,b.fecha_inicio_semana origin_week,
 b.fin_origen cutoff_date,b.fecha_inicio_semana+7*h.horizon target_week,h.horizon horizon_weeks,
 target.cantidad target_count,b.count_origin,l1.cantidad cases_lag_1,l2.cantidad cases_lag_2,
 CASE WHEN recent.known>=2 THEN recent.mean END recent_mean_3,
 b.count_origin-l1.cantidad recent_trend,recent.known known_recent_count,
 neighbors.mean neighbor_mean_origin,neighbors.known_fraction neighbor_known_fraction,
 climate.temperatura temperature_origin,climate.humedad humidity_origin,climate.precipitacion precipitation_origin,
 CASE WHEN weather.n=4 THEN weather.temp END temperature_mean_4_origin,
 CASE WHEN weather.n=4 THEN weather.rain END precipitation_sum_4_origin,
 b.estacionalidad_seno season_sin,b.estacionalidad_coseno season_cos,
 b.poblacion population,b.densidad_poblacional population_density,
 previous.temperatura temperature_lag_1,previous.humedad humidity_lag_1,previous.precipitacion precipitation_lag_1,
 NOT EXISTS(SELECT 1 FROM generate_series(0,h.horizon) n
   LEFT JOIN analytics.semana_epidemiologica cw ON cw.inicio=b.fecha_inicio_semana+7*n AND cw.calendario_version=b.calendario_version
   LEFT JOIN analytics.conteo_investigacion coverage ON coverage.dataset_version=b.dataset_version
     AND coverage.radio_id=b.radio_id AND coverage.semana_id=cw.id
   WHERE coverage.semana_id IS NULL) continuous_scope
 FROM analytics.base_investigacion b CROSS JOIN (VALUES(1),(2),(4)) h(horizon)
 LEFT JOIN analytics.semana_epidemiologica wt ON wt.inicio=b.fecha_inicio_semana+7*h.horizon AND wt.calendario_version=b.calendario_version
 LEFT JOIN analytics.semana_epidemiologica w1 ON w1.inicio=b.fecha_inicio_semana-7 AND w1.calendario_version=b.calendario_version
 LEFT JOIN analytics.semana_epidemiologica w2 ON w2.inicio=b.fecha_inicio_semana-14 AND w2.calendario_version=b.calendario_version
 LEFT JOIN analytics.conteo_investigacion target ON target.dataset_version=b.dataset_version AND target.radio_id=b.radio_id AND target.semana_id=wt.id
 LEFT JOIN analytics.conteo_investigacion l1 ON l1.dataset_version=b.dataset_version AND l1.radio_id=b.radio_id AND l1.semana_id=w1.id
 LEFT JOIN analytics.conteo_investigacion l2 ON l2.dataset_version=b.dataset_version AND l2.radio_id=b.radio_id AND l2.semana_id=w2.id
 CROSS JOIN LATERAL(SELECT count(v)::integer known,avg(v) mean FROM (VALUES(b.count_origin),(l1.cantidad),(l2.cantidad)) q(v)) recent
 CROSS JOIN LATERAL(SELECT avg(v) mean,count(v)::double precision/nullif(count(*),0) known_fraction
   FROM (SELECT nc.cantidad v FROM territory.vecindad n
     JOIN territory.miembro_universo m ON m.radio_id=n.vecino_id AND m.universo_id=b.universo_id
     LEFT JOIN analytics.semana_epidemiologica nw ON nw.inicio=b.fecha_inicio_semana AND nw.calendario_version=b.calendario_version
     LEFT JOIN analytics.conteo_investigacion nc ON nc.dataset_version=b.dataset_version AND nc.radio_id=n.vecino_id AND nc.semana_id=nw.id
     WHERE n.radio_id=b.radio_id) q) neighbors
 LEFT JOIN analytics.semana_epidemiologica origin ON origin.inicio=b.fecha_inicio_semana AND origin.calendario_version=b.calendario_version
 LEFT JOIN analytics.clima_escenario_ml climate ON climate.escenario_version=b.escenario_version AND climate.semana_id=origin.id AND climate.dias=7
 LEFT JOIN analytics.clima_escenario_ml previous ON previous.escenario_version=b.escenario_version AND previous.semana_id=w1.id AND previous.dias=7
 CROSS JOIN LATERAL(SELECT count(cs.temperatura) n,avg(cs.temperatura) temp,sum(cs.precipitacion) rain
   FROM analytics.clima_escenario_ml cs JOIN analytics.semana_epidemiologica cw ON cw.id=cs.semana_id
   WHERE cs.escenario_version=b.escenario_version AND cw.inicio IN(b.fecha_inicio_semana,b.fecha_inicio_semana-7,b.fecha_inicio_semana-14,b.fecha_inicio_semana-21)
   AND cs.dias=7 AND cs.temperatura IS NOT NULL AND cs.humedad IS NOT NULL AND cs.precipitacion IS NOT NULL) weather;

DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['analytics.escenario_investigacion','analytics.fuente_escenario_ml',
 'analytics.registro_escenario_ml','analytics.clima_escenario_ml','analytics.dataset_investigacion',
 'analytics.conteo_investigacion','analytics.modelo_investigacion','analytics.evaluacion_investigacion',
 'analytics.prediccion_investigacion'] LOOP
 EXECUTE format('CREATE TRIGGER research_immutable BEFORE UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION epidemiology.review_is_immutable()',item);
 EXECUTE format('REVOKE ALL ON %s FROM PUBLIC',item);
 EXECUTE format('GRANT SELECT,INSERT ON %s TO sigard_epi_importer',item);
 END LOOP;
END $$;
REVOKE ALL ON analytics.disponibilidad_investigacion,analytics.base_investigacion,
 analytics.investigacion_a,analytics.investigacion_b,analytics.investigacion_v3,analytics.vecindad_investigacion,
 analytics.metadatos_investigacion FROM PUBLIC;
GRANT SELECT ON analytics.escenario_investigacion,analytics.dataset_investigacion,
 analytics.clima_escenario_ml,analytics.conteo_investigacion,analytics.modelo_investigacion,
 analytics.evaluacion_investigacion,analytics.prediccion_investigacion,
 analytics.disponibilidad_investigacion,analytics.base_investigacion,
 analytics.investigacion_a,analytics.investigacion_b,analytics.investigacion_v3,analytics.vecindad_investigacion,
 analytics.metadatos_investigacion
 TO sigard_epi_analytics_reader,sigard_epi_importer;
GRANT INSERT ON analytics.prediccion_investigacion TO sigard_epi_analytics_reader;
