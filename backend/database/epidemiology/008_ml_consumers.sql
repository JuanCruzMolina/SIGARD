-- Aggregate metadata for DB-only ML consumers. No new tables or source writes.
CREATE VIEW analytics.ejecuciones_ml AS
 SELECT e.*,u.version universe_version,pt.version temporal_policy,
 pc.version classification_policy,cc.version coverage_policy
 FROM analytics.ejecucion e JOIN territory.universo u ON u.id=e.universo_id
 JOIN epidemiology.politica_temporal pt ON pt.id=e.politica_temporal_id
 JOIN epidemiology.politica_clasificacion pc ON pc.id=e.politica_clasificacion_id
 JOIN epidemiology.criterio_cobertura cc ON cc.id=e.criterio_cobertura_id;

CREATE VIEW analytics.fuentes_ml AS
 SELECT fe.ejecucion_id,fe.lote_id,a.sha256,(v.id IS NOT NULL) AS current
 FROM analytics.fuente_ejecucion fe
 JOIN ingestion.lote_importacion l ON l.id=fe.lote_id
 JOIN ingestion.archivo_fuente a ON a.id=l.archivo_id
 LEFT JOIN ingestion.lotes_sisa_vigentes v ON v.id=l.id;

-- Preserve V2's origin-admissibility rule used by V3: >= half the universe
-- with t-1 counts, compatible complete t-1 weather, and every explicit scenario
-- week from origin to target. NULL counts remain NULL; no labels are generated.
CREATE VIEW analytics.soporte_predictor_v3 AS
 SELECT e.version dataset_version,r.codigo radio_id,w.inicio origin_week,
 h.horizon horizon_weeks,
 analytics.conteo_en(e.id,r.id,w.inicio-7,w.fin) lag_1,
 climate.temperatura temperature_lag_1,climate.humedad humidity_lag_1,
 climate.precipitacion precipitation_lag_1,
 NOT EXISTS(SELECT 1 FROM generate_series(0,h.horizon) n
   LEFT JOIN analytics.semana_epidemiologica sw ON sw.inicio=w.inicio+7*n
     AND sw.calendario_version=e.calendario_version
   LEFT JOIN analytics.conteos_radio_semana sc ON sc.ejecucion_id=e.id
     AND sc.radio_id=r.id AND sc.semana_id=sw.id
   WHERE sc.cobertura_estado IS DISTINCT FROM 'experimental_assumed') continuous_scope
 FROM analytics.ejecucion e JOIN territory.universo u ON u.id=e.universo_id
 JOIN analytics.conteos_radio_semana c ON c.ejecucion_id=e.id
 JOIN territory.radio_censal r ON r.id=c.radio_id
 JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
 CROSS JOIN (VALUES(1),(2),(4)) h(horizon)
 LEFT JOIN analytics.semana_epidemiologica previous ON previous.inicio=w.inicio-7
   AND previous.calendario_version=e.calendario_version
 LEFT JOIN analytics.clima_semana climate ON climate.semana_id=previous.id
   AND climate.version=e.clima_version AND climate.compatible
   AND (e.modo='retrospective' OR climate.disponible_desde <
     (w.fin+1)::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires')
 WHERE u.version='v3-256-subset-v1';

REVOKE ALL ON analytics.ejecuciones_ml,analytics.fuentes_ml,analytics.soporte_predictor_v3 FROM PUBLIC;
GRANT SELECT ON analytics.ejecuciones_ml,analytics.fuentes_ml,analytics.soporte_predictor_v3
 TO sigard_epi_analytics_reader,sigard_epi_importer;
