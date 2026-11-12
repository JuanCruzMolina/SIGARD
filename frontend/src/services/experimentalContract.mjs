export const experimentalWarning = 'Resultados experimentales: consultas retrospectivas e inferencia local t+1 cuando está habilitada. No representan predicciones epidemiológicas validadas ni deben utilizarse para decisiones sanitarias.'
const schema = 'sigard-retrospective-spatial-score/1'
const versions = { A: ['spatial_rf_05c_v1', 'official-spatial-rf-research-0.5c.0'], B: ['spatial_rf_B_05f_v1', 'official-spatial-rf-B-research-0.5f.0'] }
function check(value) { if (!value) throw new Error('Contrato experimental incompatible; consulta bloqueada.') }

export function isLocalResearchContext(env, origin) {
  return env.DEV === true && origin === 'http://127.0.0.1:5173'
}

export function validateCatalog(catalog) {
  check(catalog?.schema_version === schema && Array.isArray(catalog.models) && catalog.models.length > 0 && catalog.models.length <= 2)
  check(new Set(catalog.models.map(m => m.model_id)).size === catalog.models.length)
  const calendar = new Map()
  for (const m of catalog.models) {
    check(versions[m.model_id]?.[0] === m.experiment_id && versions[m.model_id]?.[1] === m.training_version)
    check(Array.isArray(m.weeks) && m.weeks.length === 20)
    check(new Set(m.weeks.map(w => w.target_week_start)).size === 20)
    for (const w of m.weeks) {
      check(/^2024-\d{2}-\d{2}$/.test(w.target_week_start) && Number.isInteger(w.target_epidemiological_week))
      const previous = calendar.get(w.target_week_start)
      if (previous) for (const key of ['target_week_end', 'target_epidemiological_year', 'target_epidemiological_week', 'evaluation_partition']) check(previous[key] === w[key])
      calendar.set(w.target_week_start, w)
    }
  }
  return catalog
}

export function validateScores(collection, model, week, radios) {
  check(collection?.schema_version === schema && collection.model_id === model.model_id && collection.experiment_id === model.experiment_id && collection.training_version === model.training_version)
  check(collection.target_week_start === week && collection.calendar_version === 'ar-snvs-2020-2026-v1' && collection.territory_version === 'capital-census-2022-public-v1')
  const metadata = model.weeks?.find(w => w.target_week_start === week)
  if (metadata) for (const key of ['target_week_end', 'target_epidemiological_year', 'target_epidemiological_week', 'evaluation_partition']) check(collection[key] === metadata[key])
  check(collection.data_kind === 'official_experimental_retrospective' && collection.score_semantics === 'raw_class_1_score_uncalibrated')
  check(collection.retrospective === true && collection.operational_use_authorized === false && collection.publication_authorized === false && collection.coverage_verified === false && collection.previously_examined === true)
  check(collection.coverage_scenario === 'spatial_assumed_2024_v1' && Array.isArray(collection.interpretation_limitations) && collection.interpretation_limitations.length === 10)
  check(Array.isArray(collection.rows) && collection.rows.length === radios.length)
  const ids = new Set(radios), seen = new Set()
  for (const row of collection.rows) {
    check(typeof row.radio_censal === 'string' && ids.has(row.radio_censal) && !seen.has(row.radio_censal))
    seen.add(row.radio_censal)
    check((row.score_status === 'available' && typeof row.experimental_score === 'number' && Number.isFinite(row.experimental_score) && row.experimental_score >= 0 && row.experimental_score <= 1) || (row.score_status === 'not_computed' && row.experimental_score === null && row.score_unavailable_reason === 'frozen_score_missing'))
    check(row.data_availability?.prediction_as_of === null && row.data_availability?.operational_availability === 'not_accredited')
  }
  return collection
}

export function experimentalColor(score) {
  if (score === null || score === undefined) return '#aab2ba'
  return ['#e2dcf2', '#b29fd6', '#8160b3', '#543583'][Math.min(3, Math.floor(score * 4))]
}

// Presentation only: consume validated frozen rows, never impute an absent score.
export function scoreDifference(a, b) {
  return a?.score_status === 'available' && b?.score_status === 'available'
    && Number.isFinite(a.experimental_score) && Number.isFinite(b.experimental_score)
    ? b.experimental_score - a.experimental_score : null
}

export function differenceColor(value) {
  if (value === null || value === undefined) return '#aab2ba'
  if (value === 0) return '#fffefa'
  if (value < 0) return value < -.5 ? '#236b88' : '#b4d8e8'
  return value > .5 ? '#99501b' : '#efc391'
}

export function joinComparisonGeometry(geometry, collections, week, mode) {
  const maps = Object.fromEntries(['A', 'B'].map(id => [id,
    new Map((collections[id]?.value?.target_week_start === week && collections[id]?.value?.model_id === id
      ? collections[id].value.rows : []).map(row => [row.radio_censal, row]))]))
  return { type: 'FeatureCollection', features: geometry.features.map(feature => {
    const id = feature.properties.radio_id
    const a = maps.A.get(id), b = maps.B.get(id)
    const difference = scoreDifference(a, b)
    const row = mode === 'difference' ? null : maps[mode].get(id)
    return { type: 'Feature', geometry: feature.geometry, properties: {
      radio_id: id, target_week_start: week, research_mode: mode,
      experimental_score: row?.score_status === 'available' ? row.experimental_score : null,
      result_type: mode === 'difference' ? null : collections[mode]?.query?.result_type || null,
      score_status: mode === 'difference'
        ? collections.A?.error || collections.B?.error ? 'error' : difference !== null ? 'available' : 'not_computed'
        : collections[mode]?.error ? 'error' : row?.score_status || 'not_computed', difference,
      model_a: a, model_b: b,
    } }
  }) }
}

export const dateQueryReasons = {
  outside_calendar_coverage: 'Fecha fuera del calendario epidemiológico verificado.',
  model_not_registered: 'Modelo sin autorización de lectura en esta sesión local.',
  no_frozen_prediction: 'No existe una predicción congelada para esta semana.',
  new_inference_not_enabled: 'La inferencia nueva A/B no está habilitada.',
  temporal_provenance_not_verified: 'No está acreditada la disponibilidad de las entradas en la semana de origen.',
  outside_experiment_coverage: 'Fecha fuera de la cobertura del experimento congelado de 2024.',
  historical_input_availability_unverified: 'No hay resultado congelado y no puede acreditarse que las entradas y el estimador estuvieran disponibles en ese origen histórico.',
  horizon_not_supported: 'La inferencia nueva sólo admite la semana siguiente a la semana de origen actual (t+1).',
  recent_epidemiological_history_unavailable: 'B no dispone de una fuente reciente de presencia por radio con sus cuatro rezagos y disponibilidad temporal verificable. No se fabrican antecedentes.',
  inputs_not_available_at_cutoff: 'Las entradas o el estimador todavía no estaban disponibles en el corte de la consulta.',
  inference_runtime_unavailable: 'No está disponible el entorno ML privado requerido para ejecutar el estimador.',
  inference_runtime_incompatible: 'El entorno ML no coincide con las versiones del estimador congelado.',
  inference_busy: 'El ejecutor privado está ocupado. Reintentá la consulta.',
  inference_timeout: 'El ejecutor privado tardó demasiado. Reintentá la consulta.',
}

export function validateResolvedDate(value, requested) {
  check(value?.schema_version === 'sigard-private-spatial-date-query/1' && value.requested_date === requested)
  check(value.calendar_version === 'ar-snvs-2020-2026-v1' && value.horizon_weeks === 1)
  check((value.information_cutoff === null || (typeof value.information_cutoff === 'string' && value.information_cutoff.includes('T') && Number.isFinite(Date.parse(value.information_cutoff)))) && value.operational_use_authorized === false && value.publication_authorized === false)
  check(/^\d{4}-\d{2}-\d{2}$/.test(value.calendar_min) && /^\d{4}-\d{2}-\d{2}$/.test(value.calendar_max))
  if (value.calendar_status === 'supported') {
    check(value.target_week_start <= requested && requested <= value.target_week_end)
    check(Number.isInteger(value.target_epidemiological_year) && Number.isInteger(value.target_epidemiological_week))
    const days = (a, b) => (Date.parse(a) - Date.parse(b)) / 86400000
    check(days(value.target_week_end, value.target_week_start) === 6 && days(value.target_week_start, value.origin_week_start) === 7)
    check(days(value.origin_week_end, value.origin_week_start) === 6 && value.calendar_cutoff === value.origin_week_end)
  } else check(value.calendar_status === 'outside_calendar' && value.target_week_start === null && value.origin_week_start === null)
  return value
}

export function validateDateQuery(value, requested, model, radios, temporal) {
  validateResolvedDate(value, requested)
  check(value.model_id === model.model_id && value.experiment_id === model.experiment_id && value.training_version === model.training_version)
  check(value.territory_version === 'capital-census-2022-public-v1' && typeof value.new_inference_enabled === 'boolean')
  for (const key of ['target_week_start', 'target_week_end', 'target_epidemiological_year', 'target_epidemiological_week', 'origin_week_start', 'origin_week_end', 'calendar_status']) check(value[key] === temporal[key])
  check(Array.isArray(value.radio_ids) && value.radio_ids.length === radios.length && new Set(value.radio_ids).size === radios.length && radios.every(id => value.radio_ids.includes(id)))
  check(Array.isArray(value.blockers))
  if (value.availability === 'available') {
    check(value.blockers.length === 0 && value.calendar_status === 'supported')
    if (value.result_type === 'frozen') {
      check(value.information_cutoff === null)
      validateScores(value.result, model, value.target_week_start, radios)
    } else {
      check(value.result_type === 'experimental_inference' && value.new_inference_enabled === true)
      validateInferenceScores(value.result, value, model, radios)
    }
    for (const key of ['origin_week_start', 'origin_week_end', 'target_week_start', 'target_week_end', 'target_epidemiological_year', 'target_epidemiological_week']) check(value.result[key] === value[key])
  } else {
    check(value.availability === 'unavailable' && value.result_type === 'unavailable' && value.result === null)
    check(value.blockers.length > 0 && value.blockers.every(code => Object.hasOwn(dateQueryReasons, code)))
  }
  return value
}

export function validateInferenceScores(collection, query, model, radios) {
  check(collection?.schema_version === 'sigard-experimental-spatial-inference/1')
  check(collection.model_id === 'A' && collection.model_id === model.model_id && collection.experiment_id === model.experiment_id && collection.training_version === model.training_version)
  check(collection.territory_version === 'capital-census-2022-public-v1' && collection.calendar_version === 'ar-snvs-2020-2026-v1' && collection.horizon_weeks === 1)
  check(collection.data_kind === 'private_experimental_inference' && collection.score_semantics === 'raw_class_1_score_uncalibrated' && collection.prediction_target === 'binary_experimental_record_presence_next_week')
  check(collection.retrospective === false && collection.operational_use_authorized === false && collection.publication_authorized === false)
  const cutoff = Date.parse(query.information_cutoff)
  check(collection.information_cutoff === query.information_cutoff && Number.isFinite(cutoff))
  check(cutoff >= Date.parse(`${query.origin_week_start}T00:00:00-03:00`) && cutoff < Date.parse(`${query.target_week_start}T00:00:00-03:00`))
  const provenance = collection.provenance
  check(provenance?.historical_availability_accredited === false && provenance.model_fitted === false)
  check(provenance.availability_basis === 'local_hash_verified_observation_now' && provenance.context_semantics === 'fixed_2022_census_context_not_current_population')
  check(typeof provenance.source_snapshot_id === 'string' && provenance.source_snapshot_id.startsWith('ab-fixed-context-'))
  for (const key of ['context_available_at', 'model_available_at']) check(Number.isFinite(Date.parse(provenance[key])) && Date.parse(provenance[key]) <= cutoff)
  check(Array.isArray(collection.rows) && collection.rows.length === radios.length && new Set(collection.rows.map(row => row.radio_censal)).size === radios.length)
  const ids = new Set(radios)
  for (const row of collection.rows) {
    check(ids.has(row.radio_censal) && row.score_status === 'available' && row.score_unavailable_reason === null)
    check(typeof row.experimental_score === 'number' && Number.isFinite(row.experimental_score) && row.experimental_score >= 0 && row.experimental_score <= 1)
    check(row.data_availability?.prediction_as_of === query.information_cutoff && row.data_availability?.epidemiological_history === 'not_used_by_model' && row.data_availability?.known_lag_count === null && row.data_availability?.operational_availability === 'not_accredited')
  }
  return collection
}

export function validateComparison(value, catalog, radio, week) {
  check(value?.schema_version === schema && value.radio_censal === radio && value.target_week_start === week)
  check(Array.isArray(value.results) && value.results.length > 0 && value.results.length <= 2)
  check(new Set(value.results.map(c => c.model_id)).size === value.results.length)
  for (const c of value.results) {
    const model = catalog.models.find(m => m.model_id === c.model_id)
    check(model)
    validateScores(c, model, week, [radio])
  }
  check(value.comparable === (value.results.length === 2 && value.results.every(c => c.rows[0].score_status === 'available')))
  return value
}

export function joinExperimentalGeometry(geometry, collection) {
  const scores = new Map(collection.rows.map(r => [r.radio_censal, r]))
  return { type: 'FeatureCollection', features: geometry.features.map(f => ({ type: 'Feature', geometry: f.geometry,
    properties: { radio_id: f.properties.radio_id, ...scores.get(f.properties.radio_id), target_week_start: collection.target_week_start } })) }
}
