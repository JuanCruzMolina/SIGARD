CREATE VIEW analytics.correspondencia_universos AS
 SELECT ua.version universo_a,ub.version universo_b,r.codigo radio_codigo,r.version_geometria_id
 FROM territory.miembro_universo a JOIN territory.miembro_universo b ON b.radio_id=a.radio_id
 JOIN territory.universo ua ON ua.id=a.universo_id JOIN territory.universo ub ON ub.id=b.universo_id
 JOIN territory.radio_censal r ON r.id=a.radio_id;

CREATE VIEW analytics.ml_a AS
 SELECT c.ejecucion_id,e.version dataset_version,u.version universo_version,r.codigo radio_censal,
 w.inicio fecha_inicio_semana,w.fin fin_origen,w.inicio+7 fecha_inicio_semana_objetivo,
 target.presencia objetivo_semana_siguiente, target.cobertura_estado cobertura_objetivo,
 x.superficie_km2,x.poblacion,x.poblacion/x.superficie_km2 densidad_poblacional,
 x.cantidad_vecinos,w.numero semana_epidemiologica,
 sin(2*pi()*(w.numero-1)/w.semanas_anio) estacionalidad_seno,
 cos(2*pi()*(w.numero-1)/w.semanas_anio) estacionalidad_coseno,
 pt.version politica_temporal,pc.version politica_clasificacion,e.modo,
 e.equivalencia_ml_verificada,c.radio_id,e.corte_informacion
 FROM analytics.conteos_radio_semana c
 JOIN analytics.ejecucion e ON e.id=c.ejecucion_id
 JOIN territory.universo u ON u.id=e.universo_id
 JOIN territory.radio_censal r ON r.id=c.radio_id
 JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
 JOIN analytics.contexto_radio x ON x.universo_id=e.universo_id AND x.radio_id=c.radio_id
 JOIN epidemiology.politica_temporal pt ON pt.id=e.politica_temporal_id
 JOIN epidemiology.politica_clasificacion pc ON pc.id=e.politica_clasificacion_id
 LEFT JOIN analytics.semana_epidemiologica wt ON wt.inicio=w.inicio+7 AND wt.calendario_version=w.calendario_version
 LEFT JOIN analytics.conteos_radio_semana target ON target.ejecucion_id=c.ejecucion_id AND target.radio_id=c.radio_id AND target.semana_id=wt.id
 WHERE u.version='ab-263-master-v1';

CREATE FUNCTION analytics.presencia_en(eid bigint,rid bigint,source_week date,origin_end date)
 RETURNS integer LANGUAGE sql STABLE AS $$
 SELECT c.presencia FROM analytics.conteos_radio_semana c JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
 JOIN analytics.ejecucion e ON e.id=c.ejecucion_id
 WHERE c.ejecucion_id=eid AND c.radio_id=rid AND w.inicio=source_week AND w.calendario_version=e.calendario_version
 AND (e.modo='retrospective' OR (c.disponibilidad_verificada AND c.ultimo_disponible < (origin_end+1)::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires'))
$$;
CREATE FUNCTION analytics.conteo_en(eid bigint,rid bigint,source_week date,origin_end date)
 RETURNS integer LANGUAGE sql STABLE AS $$
 SELECT c.cantidad_registros FROM analytics.conteos_radio_semana c JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
 JOIN analytics.ejecucion e ON e.id=c.ejecucion_id
 WHERE c.ejecucion_id=eid AND c.radio_id=rid AND w.inicio=source_week AND w.calendario_version=e.calendario_version
 AND (e.modo='retrospective' OR (c.disponibilidad_verificada AND c.ultimo_disponible < (origin_end+1)::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires'))
$$;
CREATE VIEW analytics.ml_b AS
 SELECT a.*,h.l1 local_presencia_exp_rezago_1,h.l2 local_presencia_exp_rezago_2,
 h.l3 local_presencia_exp_rezago_3,h.l4 local_presencia_exp_rezago_4,
 (h.l1 IS NULL)::integer local_presencia_exp_rezago_1_missing,
 (h.l2 IS NULL)::integer local_presencia_exp_rezago_2_missing,
 (h.l3 IS NULL)::integer local_presencia_exp_rezago_3_missing,
 (h.l4 IS NULL)::integer local_presencia_exp_rezago_4_missing
 FROM analytics.ml_a a CROSS JOIN LATERAL (SELECT
 analytics.presencia_en(a.ejecucion_id,a.radio_id,a.fecha_inicio_semana-7,a.fin_origen) l1,
 analytics.presencia_en(a.ejecucion_id,a.radio_id,a.fecha_inicio_semana-14,a.fin_origen) l2,
 analytics.presencia_en(a.ejecucion_id,a.radio_id,a.fecha_inicio_semana-21,a.fin_origen) l3,
 analytics.presencia_en(a.ejecucion_id,a.radio_id,a.fecha_inicio_semana-28,a.fin_origen) l4) h;

CREATE VIEW analytics.ml_v3 AS
 SELECT e.id ejecucion_id,e.version dataset_version,u.version universo_version,r.codigo radio_id,
 w.inicio origin_week,w.fin cutoff_date,w.inicio+7*h.horizon target_week,h.horizon horizon_weeks,
 target.cantidad_registros target_count,target.cobertura_estado,
 vals.c0 count_origin,vals.c1 cases_lag_1,vals.c2 cases_lag_2,
 CASE WHEN recent.known>=2 THEN recent.mean END recent_mean_3,
 vals.c0-vals.c1 recent_trend,recent.known known_recent_count,
 neighbors.mean neighbor_mean_origin,neighbors.known_fraction neighbor_known_fraction,
 climate.temperatura temperature_origin,climate.humedad humidity_origin,climate.precipitacion precipitation_origin,
 CASE WHEN weather.n=4 THEN weather.temp END temperature_mean_4_origin,
 CASE WHEN weather.n=4 THEN weather.rain END precipitation_sum_4_origin,
 sin(2*pi()*(w.numero-1)/w.semanas_anio) season_sin,cos(2*pi()*(w.numero-1)/w.semanas_anio) season_cos,
 x.poblacion population,x.poblacion/x.superficie_km2 population_density,
 e.equivalencia_ml_verificada,e.modo,pt.version politica_temporal,pc.version politica_clasificacion
 FROM analytics.conteos_radio_semana c JOIN analytics.ejecucion e ON e.id=c.ejecucion_id
 JOIN territory.universo u ON u.id=e.universo_id JOIN territory.radio_censal r ON r.id=c.radio_id
 JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
 JOIN analytics.contexto_radio x ON x.universo_id=e.universo_id AND x.radio_id=c.radio_id
 JOIN epidemiology.politica_temporal pt ON pt.id=e.politica_temporal_id
 JOIN epidemiology.politica_clasificacion pc ON pc.id=e.politica_clasificacion_id
 CROSS JOIN (VALUES(1),(2),(4)) h(horizon)
 LEFT JOIN analytics.semana_epidemiologica wt ON wt.inicio=w.inicio+7*h.horizon AND wt.calendario_version=w.calendario_version
 LEFT JOIN analytics.conteos_radio_semana target ON target.ejecucion_id=c.ejecucion_id AND target.radio_id=c.radio_id AND target.semana_id=wt.id
 CROSS JOIN LATERAL (SELECT analytics.conteo_en(e.id,c.radio_id,w.inicio,w.fin) c0,
 analytics.conteo_en(e.id,c.radio_id,w.inicio-7,w.fin) c1,
 analytics.conteo_en(e.id,c.radio_id,w.inicio-14,w.fin) c2) vals
 CROSS JOIN LATERAL (SELECT count(v)::integer known,avg(v) mean FROM (VALUES(vals.c0),(vals.c1),(vals.c2)) q(v)) recent
 CROSS JOIN LATERAL (SELECT avg(v) mean,count(v)::double precision/nullif(count(*),0) known_fraction
  FROM (SELECT analytics.conteo_en(e.id,n.vecino_id,w.inicio,w.fin) v FROM territory.vecindad n
  JOIN territory.miembro_universo m ON m.radio_id=n.vecino_id AND m.universo_id=e.universo_id WHERE n.radio_id=c.radio_id) q) neighbors
 LEFT JOIN analytics.clima_semana climate ON climate.version=e.clima_version AND climate.semana_id=w.id AND climate.compatible
 AND (e.modo='retrospective' OR climate.disponible_desde<(w.fin+1)::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires')
 CROSS JOIN LATERAL (SELECT count(cs.temperatura) n,avg(cs.temperatura) temp,sum(cs.precipitacion) rain
  FROM analytics.clima_semana cs JOIN analytics.semana_epidemiologica cw ON cw.id=cs.semana_id
  WHERE cs.version=e.clima_version AND cs.compatible AND cw.inicio IN(w.inicio,w.inicio-7,w.inicio-14,w.inicio-21)
  AND cs.temperatura IS NOT NULL AND cs.humedad IS NOT NULL AND cs.precipitacion IS NOT NULL
  AND (e.modo='retrospective' OR cs.disponible_desde<(w.fin+1)::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires')) weather
 WHERE u.version='v3-256-subset-v1';

-- View rights do not grant access to staging/addresses/individual coordinates.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA analytics,ingestion FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA analytics TO sigard_epi_analytics_reader,sigard_epi_importer;
GRANT SELECT ON analytics.ml_a,analytics.ml_b,analytics.ml_v3,analytics.correspondencia_universos TO sigard_epi_analytics_reader,sigard_epi_importer;
