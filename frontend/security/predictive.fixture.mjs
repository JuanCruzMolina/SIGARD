// Generated fictional final-module transport, isolated from project results.
import { catalog as previous, geometry, metadata as previousMetadata, comparison, summary } from './backtest.fixture.mjs'
export const catalog = { ...previous, weeks: previous.weeks.map(w => ({ ...w, ml_availability: { presence: w.target_year === 2024 ? 'available' : 'not_available', quantity: w.target_year === 2024 ? 'available' : 'not_available' } })), module_version: 'sigard-predictive-experimental/1', active_methods: { presence: 'presence_seasonal', quantity: 'count_latest' }, training_enabled: false, operational_enabled: false }
const mlRows = rows => rows.filter(r => r.ml?.quantity !== null).map(r => ({ ...r, predicted: r.ml, confusion: r.ml.confusion }))
const protect = (doc, mode) => {
  const result = structuredClone(doc)
  result.module_version = catalog.module_version
  result.result_type = 'historical_h1_statistical_reference'
  result.disclosure = { mode, minimum_count: 5, policy_version: 'sigard-local-presentation-minimum5-v1', metrics_scope: mode === 'private' ? 'all_comparable' : 'disclosable_subset_not_full_study' }
  result.climate = { availability_status: 'available', origin_week: doc.origin_week, origin_end: doc.origin_end, period_end: doc.origin_end, temperature_mean: 20, humidity_mean: 50, precipitation_total: 2, days: 7 }
  if (mode === 'presentation') {
    result.department = Object.fromEntries(Object.keys(result.department).map(k => [k, null]))
    for (const r of result.rows) {
      if ([r.observed.quantity, r.predicted.quantity, r.baseline.quantity, r.observed.assigned_records].some(v => v !== null && v < 5)) {
        if (!['outside_common_territory', 'outside_coverage'].includes(r.availability_status)) r.availability_status = 'privacy_suppressed'
        r.predicted = { presence: null, presence_score: null, quantity: null }; r.observed = { presence: null, quantity: null, assigned_records: null }; r.baseline.quantity = null
        r.presence_threshold = null; r.confusion = null; r.difference = null; r.absolute_error = null
      }
      r.observed.assigned_records = null; r.territorial_quality = 'withheld'; r.coverage_status = 'withheld'; r.zero_provenance = null
    }
  }
  result.metrics = summary(result.rows)
  result.ml = Object.fromEntries(['presence', 'quantity'].map(c => [c, doc.target_year === 2024
    ? { availability_status: 'available', method: c === 'presence' ? 'rf_A_epi_climate' : 'residual_h1', state: 'experimental_evaluated', model_version: 'FICTIONAL', fit_last_target_end: doc.fit_last_target_end, calibrated: false, features: ['FICTIONAL_temperature_origin'], artifact_sha256: 'f'.repeat(64) }
    : { availability_status: 'not_available', reason: 'FICTIONAL_missing_saved_prediction' }]))
  for (const r of result.rows) {
    const available = doc.target_year === 2024 && r.availability_status === 'available'
    r.ml = { presence: available ? r.predicted.presence : null, presence_score: available ? r.predicted.presence_score : null,
      quantity: available ? r.predicted.quantity + .25 : null, presence_threshold: available ? r.presence_threshold : null,
      confusion: available ? r.confusion : null, difference: available ? r.difference + .25 : null,
      absolute_error: available ? Math.abs(r.difference + .25) : null }
    r.ml_availability = { presence: available ? 'available' : 'not_available', quantity: available ? 'available' : 'not_available' }
  }
  result.ml_metrics = summary(mlRows(result.rows))
  result.ml_metrics.presence.n = mlRows(result.rows).length
  result.ml_metrics.presence.calibration = []
  return result
}
function week(w, mode) {
  const doc = comparison(w)
  if (w.target_year === 2024 && w.target_epi_week <= 24) {
    // SE 15 has one extra disclosable radio, so the fictional default week is unambiguous.
    for (const [i, observed, predicted] of [[0, 12, 7], [1, 7, 6], [2, 6, 8], ...(w.target_epi_week === 15 ? [[3, 9, 6]] : [])]) {
      const r = doc.rows[i]; r.observed.quantity = observed; r.observed.presence = 1; r.observed.assigned_records = observed
      r.predicted.quantity = predicted; r.baseline.quantity = predicted; r.confusion = r.predicted.presence ? 'TP' : 'FN'
      r.difference = predicted - observed; r.absolute_error = Math.abs(r.difference)
    }
    const total = doc.rows.slice(0, 4).reduce((sum, r) => sum + r.observed.quantity, 0)
    doc.department.observed_total = total; doc.department.assigned_common_total = total
  }
  return protect(doc, mode)
}
export function finalFixtureResponse(path) {
  const url = new URL(path, 'http://127.0.0.1:8765'), name = url.pathname.split('/').at(-1), mode = url.searchParams.get('disclosure') || 'presentation'
  if (name === 'calendar') return catalog
  if (name === 'geometry') return geometry
  if (name === 'metadata') return { ...previousMetadata, module_version: catalog.module_version, climate_usage: 'context_only_not_used_by_selected_methods',
    method_labels: { presence: 'FICTIONAL seasonal label', quantity: 'FICTIONAL latest label' }, experimental_methods: { presence: 'rf_A_epi_climate', quantity: 'residual_h1' } }
  if (name === 'comparison') return week(catalog.weeks.find(w => w.target_year === Number(url.searchParams.get('year')) && w.target_epi_week === Number(url.searchParams.get('week'))), mode)
  if (name === 'history') {
    const start = url.searchParams.get('start'), end = url.searchParams.get('end'), radio = url.searchParams.get('radio')
    const docs = catalog.weeks.filter(w => w.target_week >= start && w.target_week <= end).map(w => week(w, mode))
    const all = [], byYear = {}
    const series = docs.map(doc => {
      const rows = doc.rows.filter(r => !radio || r.radio_id === radio); all.push(...rows); (byYear[doc.target_year] ??= []).push(...rows)
      const m = summary(rows); const observed = rows.filter(r => r.common_mask).map(r => r.observed.quantity)
      const complete = observed.length && observed.every(v => v !== null)
      return { ...doc, rows: undefined, observed: complete ? observed.reduce((a, b) => a + b, 0) : mode === 'presentation' ? m.totals.observed : null,
        predicted: m.totals.predicted, baseline: m.totals.baseline, metrics: m, n_comparable: m.n_comparable,
        ml_predicted: summary(mlRows(rows)).totals.predicted, ml_metrics: summary(mlRows(rows)) }
    })
    return { ...previous, module_version: catalog.module_version, start, end, selected_radio: radio, series, metrics: summary(all), by_year: Object.fromEntries(Object.entries(byYear).map(([y, rows]) => [y, summary(rows)])), disclosure: { mode } }
  }
  throw new Error('Unknown final fictional endpoint')
}
