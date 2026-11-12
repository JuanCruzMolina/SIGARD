CREATE TABLE analytics.motor_campania (
 version text PRIMARY KEY,
 dataset_version text NOT NULL REFERENCES analytics.consolidacion_dataset,
 protocolo jsonb NOT NULL,
 protocolo_sha256 char(64) NOT NULL,
 dataset_sha256 char(64) NOT NULL,
 codigo_sha256 jsonb NOT NULL,
 entorno jsonb NOT NULL,
 horizonte integer NOT NULL DEFAULT 1 CHECK(horizonte=1),
 autorizacion text NOT NULL CHECK(autorizacion<>''),
 creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE analytics.motor_modelo (
 version text PRIMARY KEY,
 campania_version text NOT NULL REFERENCES analytics.motor_campania,
 metodo text NOT NULL CHECK(metodo IN ('rf_A_reference','rf_A_epi_climate','rf_A_epi_no_climate','residual_h1')),
 capacidad text NOT NULL CHECK(capacidad IN ('presence','counts')),
 bloque text NOT NULL,
 nivel text NOT NULL CHECK(nivel IN ('development_fold','comparison_fold','final_refit')),
 ultimo_objetivo_ajuste date NOT NULL,
 artefacto bytea NOT NULL,
 artefacto_sha256 char(64) NOT NULL,
 metadatos jsonb NOT NULL,
 UNIQUE(campania_version,bloque,metodo),
 CHECK((capacidad='counts')=(metodo='residual_h1'))
);
CREATE TABLE analytics.motor_evaluacion (
 campania_version text REFERENCES analytics.motor_campania,
 etapa text NOT NULL CHECK(etapa IN ('development','decision','comparison_2024','final_refit','closure')),
 resultado jsonb NOT NULL,
 resultado_sha256 char(64) NOT NULL,
 creado_en timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(campania_version,etapa)
);
CREATE TABLE analytics.motor_prediccion (
 campania_version text REFERENCES analytics.motor_campania,
 radio_id bigint REFERENCES territory.radio_censal,
 origen date NOT NULL,
 semana_objetivo date NOT NULL,
 bloque text NOT NULL,
 presencia jsonb NOT NULL,
 umbrales jsonb NOT NULL,
 cantidad jsonb NOT NULL,
 PRIMARY KEY(campania_version,radio_id,origen),
 CHECK(semana_objetivo=origen+7)
);
CREATE FUNCTION analytics.check_motor_prediction() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (SELECT count(*) FROM analytics.motor_modelo m
   WHERE m.campania_version=NEW.campania_version AND m.bloque=NEW.bloque
   AND m.ultimo_objetivo_ajuste<NEW.origen-28)<>4
 THEN RAISE EXCEPTION 'motor_prediction_requires_four_purged_registered_methods'; END IF;
 IF NOT EXISTS(SELECT 1 FROM analytics.motor_campania c
   JOIN analytics.consolidacion_dataset d ON d.version=c.dataset_version
   JOIN analytics.consolidacion_territorio t ON t.dataset_version=d.version AND t.radio_id=NEW.radio_id AND t.mascara_comun
   JOIN analytics.semana_epidemiologica w ON w.calendario_version=d.calendario_version
     AND w.inicio=NEW.semana_objetivo AND w.anio BETWEEN 2020 AND 2024
   WHERE c.version=NEW.campania_version AND NOT EXISTS(
      SELECT 1 FROM analytics.consolidacion_registro r WHERE r.dataset_version=d.version
      AND r.semana_id=w.id AND r.elegible AND r.radio_id IS NULL))
 THEN RAISE EXCEPTION 'motor_prediction_outside_covered_research_target'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_each_text(NEW.presencia) p WHERE p.value::double precision NOT BETWEEN 0 AND 1)
 OR EXISTS(SELECT 1 FROM jsonb_each_text(NEW.cantidad) p WHERE p.value::double precision<0)
 THEN RAISE EXCEPTION 'motor_prediction_value_outside_domain'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER motor_prediction_scope BEFORE INSERT ON analytics.motor_prediccion
 FOR EACH ROW EXECUTE FUNCTION analytics.check_motor_prediction();
DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['analytics.motor_campania','analytics.motor_modelo',
 'analytics.motor_evaluacion','analytics.motor_prediccion'] LOOP
 EXECUTE format('CREATE TRIGGER motor_immutable BEFORE UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION epidemiology.review_is_immutable()',item);
 EXECUTE format('REVOKE ALL ON %s FROM PUBLIC',item);
 EXECUTE format('GRANT SELECT,INSERT ON %s TO sigard_epi_importer',item);
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION analytics.check_motor_prediction() FROM PUBLIC;
GRANT SELECT ON analytics.motor_campania,analytics.motor_evaluacion,analytics.motor_prediccion TO sigard_epi_analytics_reader;
