export const experimentalWarning = 'Resultados experimentales retrospectivos. No representan predicciones epidemiológicas validadas ni deben utilizarse para decisiones sanitarias.'
const schema = 'sigard-retrospective-spatial-score/1'
const versions = { A: ['spatial_rf_05c_v1', 'official-spatial-rf-research-0.5c.0'], B: ['spatial_rf_B_05f_v1', 'official-spatial-rf-B-research-0.5f.0'] }
function check(value) { if (!value) throw new Error('Contrato experimental incompatible; consulta bloqueada.') }

export function isLocalResearchContext(env, origin) {
  return env.DEV === true && origin === 'http://127.0.0.1:5173'
}

export function validateCatalog(catalog) {
  check(catalog?.schema_version === schema && Array.isArray(catalog.models) && catalog.models.length > 0 && catalog.models.length <= 2)
  check(new Set(catalog.models.map(m => m.model_id)).size === catalog.models.length)
  for (const m of catalog.models) {
    check(versions[m.model_id]?.[0] === m.experiment_id && versions[m.model_id]?.[1] === m.training_version)
    check(Array.isArray(m.weeks) && m.weeks.length === 20)
    check(new Set(m.weeks.map(w => w.target_week_start)).size === 20)
    for (const w of m.weeks) check(/^2024-\d{2}-\d{2}$/.test(w.target_week_start) && Number.isInteger(w.target_epidemiological_week))
  }
  return catalog
}

export function validateScores(collection, model, week, radios) {
  check(collection?.schema_version === schema && collection.model_id === model.model_id && collection.experiment_id === model.experiment_id && collection.training_version === model.training_version)
  check(collection.target_week_start === week && collection.calendar_version === 'ar-snvs-2020-2026-v1' && collection.territory_version === 'capital-census-2022-public-v1')
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
