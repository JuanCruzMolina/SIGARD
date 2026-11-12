-- Additive stage 1. One reviewed record selection; no persisted radio/week grid.
CREATE TABLE analytics.consolidacion_dataset (
 version text PRIMARY KEY,
 politica_version text NOT NULL,
 calendario_version text NOT NULL,
 resolucion_version text NOT NULL REFERENCES epidemiology.version_resolucion,
 universo_id bigint NOT NULL REFERENCES territory.universo,
 clima_lote_id bigint NOT NULL REFERENCES ingestion.lote_complementario,
 contrato jsonb NOT NULL,
 entrada_sha256 char(64) NOT NULL CHECK(entrada_sha256 ~ '^[a-f0-9]{64}$'),
 creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE analytics.consolidacion_fuente (
 dataset_version text REFERENCES analytics.consolidacion_dataset,
 lote_id bigint REFERENCES ingestion.lote_importacion,
 anio_entrega integer NOT NULL CHECK(anio_entrega BETWEEN 2020 AND 2024),
 fuente_sha256 char(64) NOT NULL,
 PRIMARY KEY(dataset_version,lote_id)
);
CREATE TABLE analytics.consolidacion_registro (
 dataset_version text REFERENCES analytics.consolidacion_dataset,
 registro_id bigint REFERENCES epidemiology.registro_epidemiologico,
 lote_id bigint NOT NULL,
 fecha_referencia date, semana_id bigint REFERENCES analytics.semana_epidemiologica,
 tipo_fecha text, clases_originales jsonb NOT NULL, clases_revisadas jsonb NOT NULL,
 elegible boolean NOT NULL, positivo_sigard boolean NOT NULL,
 motivo text NOT NULL, comprobaciones jsonb NOT NULL,
 asignacion_id bigint REFERENCES territory.asignacion_radio,
 radio_id bigint REFERENCES territory.radio_censal,
 calidad_geografica text NOT NULL CHECK(calidad_geografica IN ('approximate','provisional','verified','unassigned')),
 disponible_desde timestamptz,
 PRIMARY KEY(dataset_version,registro_id),
 FOREIGN KEY(dataset_version,lote_id) REFERENCES analytics.consolidacion_fuente,
 CHECK(positivo_sigard=elegible),
 CHECK(NOT elegible OR (fecha_referencia IS NOT NULL AND semana_id IS NOT NULL AND motivo='included')),
 CHECK(elegible OR motivo<>'included'),
 CHECK((radio_id IS NULL)=(calidad_geografica='unassigned'))
);
CREATE INDEX ix_consolidacion_selection_week ON analytics.consolidacion_registro(dataset_version,semana_id,radio_id) WHERE elegible;
CREATE TABLE analytics.consolidacion_territorio (
 dataset_version text REFERENCES analytics.consolidacion_dataset,
 radio_id bigint REFERENCES territory.radio_censal,
 en_ab boolean NOT NULL, en_v3 boolean NOT NULL, mascara_comun boolean NOT NULL,
 motivo text NOT NULL, evidencia jsonb NOT NULL,
 PRIMARY KEY(dataset_version,radio_id), CHECK(NOT mascara_comun OR (en_ab AND en_v3))
);
CREATE TABLE analytics.consolidacion_clima (
 dataset_version text REFERENCES analytics.consolidacion_dataset,
 inicio date NOT NULL CHECK(extract(dow FROM inicio)=0),
 fin date NOT NULL, dias integer NOT NULL CHECK(dias BETWEEN 1 AND 7),
 temperatura double precision, humedad double precision, precipitacion double precision,
 disponible_desde timestamptz,
 PRIMARY KEY(dataset_version,inicio), CHECK(fin=inicio+6),
 CHECK(dias=7 OR (temperatura IS NULL AND humedad IS NULL AND precipitacion IS NULL)),
 CHECK(precipitacion IS NULL OR precipitacion>=0),
 CHECK(humedad IS NULL OR humedad BETWEEN 0 AND 100)
);

-- All observations stay private; aggregation counts records, not cells.
CREATE VIEW analytics.consolidacion_departamento AS
 WITH totals AS (
 SELECT dataset_version,semana_id,count(*)::integer cantidad,
 count(*) FILTER(WHERE radio_id IS NULL)::integer sin_radio,
 count(*) FILTER(WHERE calidad_geografica='approximate')::integer aproximados,
 CASE WHEN count(disponible_desde)=count(*) THEN max(disponible_desde) END disponible_desde
 FROM analytics.consolidacion_registro WHERE elegible GROUP BY 1,2)
 SELECT d.version dataset_version,w.id semana_id,w.anio,w.numero,w.inicio,w.fin,
 w.anio BETWEEN 2020 AND 2024 cubierto,
 coalesce(t.cantidad,0) registros_observados,
 CASE WHEN w.anio BETWEEN 2020 AND 2024 THEN coalesce(t.cantidad,0) END cantidad_sigard,
 CASE WHEN w.anio BETWEEN 2020 AND 2024 THEN (coalesce(t.cantidad,0)>0)::integer END presencia_sigard,
 CASE WHEN w.anio NOT BETWEEN 2020 AND 2024 THEN 'out_of_coverage'
      WHEN coalesce(t.cantidad,0)=0 THEN 'covered_assumed_zero' ELSE 'covered_observed' END cobertura_estado,
 CASE WHEN w.anio BETWEEN 2020 AND 2024 AND coalesce(t.cantidad,0)=0
      THEN 'project_owner_declared_coverage_2020_2024' END procedencia_cero,
 coalesce(t.sin_radio,0) registros_sin_radio,coalesce(t.aproximados,0) registros_aproximados,
 t.disponible_desde,d.politica_version,d.entrada_sha256
 FROM analytics.consolidacion_dataset d
 JOIN analytics.semana_epidemiologica w ON w.calendario_version=d.calendario_version
 LEFT JOIN totals t ON t.dataset_version=d.version AND t.semana_id=w.id;

CREATE VIEW analytics.consolidacion_radio_semana AS
 WITH assigned AS (
 SELECT dataset_version,semana_id,radio_id,count(*)::integer cantidad,
 count(*) FILTER(WHERE calidad_geografica='approximate')::integer aproximados,
 count(*) FILTER(WHERE calidad_geografica='provisional')::integer provisionales,
 count(*) FILTER(WHERE calidad_geografica='verified')::integer verificados
 FROM analytics.consolidacion_registro WHERE elegible AND radio_id IS NOT NULL GROUP BY 1,2,3)
 SELECT w.dataset_version,w.semana_id,w.anio,w.numero,w.inicio,w.fin,
 r.id radio_id,r.codigo radio_codigo,g.version territorio_version,g.fuente_sha256 territorio_sha256,
 t.en_ab,t.en_v3,t.mascara_comun,t.motivo motivo_mascara,
 coalesce(a.cantidad,0) registros_asignados,
 coalesce(a.aproximados,0) registros_aproximados,
 coalesce(a.provisionales,0) registros_provisionales,
 coalesce(a.verificados,0) registros_verificados,
 w.registros_sin_radio,
 CASE WHEN w.cubierto AND t.mascara_comun AND w.registros_sin_radio=0 THEN coalesce(a.cantidad,0) END cantidad_sigard,
 CASE WHEN w.cubierto AND t.mascara_comun AND coalesce(a.cantidad,0)>0 THEN 1
      WHEN w.cubierto AND t.mascara_comun AND w.registros_sin_radio=0 THEN 0 END presencia_sigard,
 CASE WHEN w.cubierto AND t.mascara_comun AND w.registros_sin_radio=0 AND w.registros_aproximados=0
      THEN coalesce(a.provisionales,0)+coalesce(a.verificados,0) END cantidad_mayor_confianza,
 CASE WHEN NOT w.cubierto THEN 'out_of_coverage' WHEN NOT t.mascara_comun THEN 'outside_common_territory'
      WHEN w.registros_sin_radio>0 THEN 'territorial_uncertainty'
      WHEN coalesce(a.cantidad,0)=0 THEN 'covered_assumed_zero' ELSE 'covered_observed' END cobertura_estado,
 CASE WHEN w.cubierto AND t.mascara_comun AND w.registros_sin_radio=0 AND coalesce(a.cantidad,0)=0
      THEN 'project_owner_declared_coverage_2020_2024' END procedencia_cero,
 CASE WHEN coalesce(a.aproximados,0)>0 THEN 'approximate'
      WHEN coalesce(a.provisionales,0)>0 THEN 'provisional'
      WHEN coalesce(a.verificados,0)>0 THEN 'verified' ELSE 'no_assigned_record' END calidad_geografica,
 x.poblacion poblacion_contexto_2022,x.superficie_km2,x.cantidad_vecinos,
 x.fuente_sha256 contexto_sha256,x.disponible_desde censo_disponible_desde,
 CASE WHEN x.disponible_desde IS NOT NULL AND extract(year FROM w.fin)>=2022
      AND x.disponible_desde < ((w.fin+1)::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires')
      THEN x.poblacion END poblacion_predictor_asof,
 c.temperatura,c.humedad,c.precipitacion,c.dias clima_dias,c.disponible_desde clima_disponible_desde,
 cl1.temperatura temperatura_lag_1,cl1.humedad humedad_lag_1,cl1.precipitacion precipitacion_lag_1,
 CASE WHEN hist.n=4 THEN hist.temp END temperatura_media_4,
 CASE WHEN hist.n=4 THEN hist.rain END precipitacion_suma_4,
 history.n clima_historia_semanas,history.temp temperatura_historia_previa,
 history.humidity humedad_historia_previa,history.rain precipitacion_media_historia_previa,
 history.last_day clima_historia_hasta,
 w.fin predictor_periodo_hasta,
 false disponibilidad_operativa_acreditada,
 w.disponible_desde registros_disponible_desde,w.politica_version,w.entrada_sha256,
 d.clima_lote_id,cf.sha256 clima_fuente_sha256
 FROM analytics.consolidacion_departamento w
 JOIN analytics.consolidacion_dataset d ON d.version=w.dataset_version
 JOIN analytics.consolidacion_territorio t ON t.dataset_version=d.version
 JOIN territory.radio_censal r ON r.id=t.radio_id
 JOIN territory.version_geometria g ON g.id=r.version_geometria_id
 LEFT JOIN analytics.contexto_radio x ON x.universo_id=d.universo_id AND x.radio_id=r.id
 LEFT JOIN assigned a ON a.dataset_version=d.version AND a.semana_id=w.semana_id AND a.radio_id=r.id
 JOIN ingestion.lote_complementario cb ON cb.id=d.clima_lote_id
 JOIN ingestion.archivo_fuente cf ON cf.id=cb.archivo_id
 LEFT JOIN analytics.consolidacion_clima c ON c.dataset_version=d.version AND c.inicio=w.inicio
 LEFT JOIN analytics.consolidacion_clima cl1 ON cl1.dataset_version=d.version AND cl1.inicio=w.inicio-7
 LEFT JOIN LATERAL(SELECT count(*) n,avg(temperatura) temp,sum(precipitacion) rain
   FROM analytics.consolidacion_clima cw WHERE cw.dataset_version=d.version
   AND cw.inicio IN(w.inicio,w.inicio-7,w.inicio-14,w.inicio-21)
   AND cw.dias=7 AND cw.temperatura IS NOT NULL AND cw.humedad IS NOT NULL AND cw.precipitacion IS NOT NULL) hist ON true
 LEFT JOIN LATERAL(SELECT count(*) n,avg(temperatura) temp,avg(humedad) humidity,avg(precipitacion) rain,max(fin) last_day
   FROM analytics.consolidacion_clima cw WHERE cw.dataset_version=d.version AND cw.fin<w.inicio
   AND cw.dias=7 AND cw.temperatura IS NOT NULL AND cw.humedad IS NOT NULL AND cw.precipitacion IS NOT NULL) history ON true;

-- Predictors in a separate view never join a future outcome.
CREATE VIEW analytics.consolidacion_predictores AS
 SELECT b.dataset_version,b.radio_id,b.radio_codigo,b.territorio_version,
 b.anio,b.numero,b.inicio origen,b.fin cierre_origen,b.predictor_periodo_hasta,
 b.mascara_comun,b.cantidad_sigard conteo_origen,b.presencia_sigard presencia_origen,
 lag.cantidad_sigard conteo_lag_1,
 b.temperatura,b.humedad,b.precipitacion,b.temperatura_lag_1,b.humedad_lag_1,b.precipitacion_lag_1,
 b.temperatura_media_4,b.precipitacion_suma_4,
 b.clima_historia_semanas,b.temperatura_historia_previa,b.humedad_historia_previa,
 b.precipitacion_media_historia_previa,b.clima_historia_hasta,
 b.poblacion_predictor_asof,
 sin(2*pi()*b.numero/w.semanas_anio) estacionalidad_seno,
 cos(2*pi()*b.numero/w.semanas_anio) estacionalidad_coseno,
 b.cobertura_estado,b.calidad_geografica,b.clima_dias,
 b.censo_disponible_desde,b.clima_disponible_desde,b.registros_disponible_desde,
 b.disponibilidad_operativa_acreditada,b.politica_version,b.entrada_sha256
 FROM analytics.consolidacion_radio_semana b
 JOIN analytics.semana_epidemiologica w ON w.id=b.semana_id
 LEFT JOIN analytics.consolidacion_radio_semana lag ON lag.dataset_version=b.dataset_version
   AND lag.radio_id=b.radio_id AND lag.inicio=b.inicio-7;

CREATE VIEW analytics.consolidacion_entrenamiento AS
 SELECT p.*,p.origen+7 semana_objetivo,t.fin cierre_objetivo,
 t.cantidad_sigard objetivo_cantidad,t.presencia_sigard objetivo_presencia,
 t.cobertura_estado cobertura_objetivo,t.procedencia_cero procedencia_cero_objetivo
 FROM analytics.consolidacion_predictores p
 LEFT JOIN analytics.consolidacion_radio_semana t ON t.dataset_version=p.dataset_version
   AND t.radio_id=p.radio_id AND t.inicio=p.origen+7;

CREATE FUNCTION analytics.check_consolidation_record() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM epidemiology.registro_epidemiologico r JOIN ingestion.fila_staging s ON s.id=r.fila_id
   WHERE r.id=NEW.registro_id AND s.lote_id=NEW.lote_id) THEN RAISE EXCEPTION 'consolidation_source_mismatch'; END IF;
 IF NEW.clases_originales IS DISTINCT FROM (SELECT coalesce(jsonb_agg(c.valor_literal ORDER BY c.id),'[]'::jsonb)
   FROM epidemiology.clasificacion_registro c WHERE c.registro_id=NEW.registro_id)
 THEN RAISE EXCEPTION 'consolidation_original_classification_mismatch'; END IF;
 IF NEW.semana_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM analytics.semana_epidemiologica w
   JOIN analytics.consolidacion_dataset d ON d.version=NEW.dataset_version AND d.calendario_version=w.calendario_version
   WHERE w.id=NEW.semana_id AND NEW.fecha_referencia BETWEEN w.inicio AND w.fin)
 THEN RAISE EXCEPTION 'consolidation_date_mismatch'; END IF;
 IF NEW.elegible AND NOT EXISTS(SELECT 1 FROM analytics.semana_epidemiologica w
   WHERE w.id=NEW.semana_id AND w.anio BETWEEN 2020 AND 2024)
 THEN RAISE EXCEPTION 'consolidation_scope_mismatch'; END IF;
 IF NEW.radio_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM territory.asignacion_radio a
   JOIN territory.geocodificacion g ON g.id=a.geocodificacion_id
   JOIN analytics.consolidacion_dataset d ON d.version=NEW.dataset_version
   LEFT JOIN territory.revision_asignacion rev ON rev.asignacion_id=a.id AND rev.version=d.resolucion_version
   LEFT JOIN territory.candidato_asignacion ca ON ca.asignacion_id=a.id AND ca.seleccionado
   WHERE a.id=NEW.asignacion_id AND g.registro_id=NEW.registro_id
   AND CASE WHEN rev.version IS NOT NULL THEN rev.radio_id WHEN a.estado='verified' THEN ca.radio_id END=NEW.radio_id
   AND CASE WHEN rev.version IS NOT NULL THEN CASE rev.estado WHEN 'point_only' THEN 'approximate'
     WHEN 'unique_provisional' THEN 'provisional' ELSE 'unassigned' END
     WHEN a.estado='verified' THEN 'verified' ELSE 'unassigned' END=NEW.calidad_geografica)
 THEN RAISE EXCEPTION 'consolidation_assignment_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER consolidation_record_source BEFORE INSERT ON analytics.consolidacion_registro
 FOR EACH ROW EXECUTE FUNCTION analytics.check_consolidation_record();

DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['analytics.consolidacion_dataset','analytics.consolidacion_fuente',
 'analytics.consolidacion_registro','analytics.consolidacion_territorio','analytics.consolidacion_clima'] LOOP
 EXECUTE format('CREATE TRIGGER consolidation_immutable BEFORE UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION epidemiology.review_is_immutable()',item);
 EXECUTE format('REVOKE ALL ON %s FROM PUBLIC',item);
 EXECUTE format('GRANT SELECT,INSERT ON %s TO sigard_epi_importer',item);
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION analytics.check_consolidation_record() FROM PUBLIC;
REVOKE ALL ON analytics.consolidacion_departamento,analytics.consolidacion_radio_semana,
 analytics.consolidacion_predictores,analytics.consolidacion_entrenamiento FROM PUBLIC;
GRANT SELECT ON analytics.consolidacion_dataset,analytics.consolidacion_territorio,
 analytics.consolidacion_clima,analytics.consolidacion_departamento,analytics.consolidacion_radio_semana,
 analytics.consolidacion_predictores,analytics.consolidacion_entrenamiento TO sigard_epi_analytics_reader,sigard_epi_importer;
