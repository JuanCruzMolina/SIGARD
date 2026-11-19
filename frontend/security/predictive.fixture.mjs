// Generated fictional final-module transport, isolated from project results.
import { catalog as previous, geometry, metadata as previousMetadata, comparison, summary } from './backtest.fixture.mjs'
// Candidate ids match the real method names only so their help texts resolve; every value is fictional.
export const candidates = [
  { id: 'rf_A_epi_climate', capability: 'presence', state: 'experimental_evaluated', decision_rule: { type: 'threshold' }, campaign: 'FICTIONAL-v1', calibrated: false, promotion: { decision: 'not_promoted' } },
  { id: 'residual_h1', capability: 'quantity', state: 'experimental_evaluated', decision_rule: { type: 'count_estimate' }, campaign: 'FICTIONAL-v1', calibrated: false, promotion: { decision: 'not_promoted' } },
  { id: 'rf_v2_city_propensity', capability: 'presence', state: 'experimental_not_promoted', decision_rule: { type: 'top_k', k: 10, scope: 'per_target_week_common_territory' }, campaign: 'FICTIONAL-v2', calibrated: false, promotion: { decision: 'not_promoted' } },
  { id: 'residual_v2', capability: 'quantity', state: 'experimental_not_promoted', decision_rule: { type: 'count_estimate' }, campaign: 'FICTIONAL-v2', calibrated: false, promotion: { decision: 'not_promoted' } },
]
export const defaults = { presence: 'rf_v2_city_propensity', quantity: 'residual_v2' }
const availability = w => Object.fromEntries(candidates.map(c => [c.id, w.target_year === 2024 ? 'available' : 'not_available']))
export const catalog = { ...previous, weeks: previous.weeks.map(w => ({ ...w, ml_availability: availability(w) })), module_version: 'sigard-predictive-experimental/2', active_methods: { presence: 'presence_seasonal', quantity: 'count_latest' }, experimental_candidates: candidates, default_candidates: defaults, training_enabled: false, operational_enabled: false }
const empty = () => ({ presence_score: null, presence: null, presence_threshold: null, topk_rank: null, onset_eligible: null, quantity: null, confusion: null, difference: null, absolute_error: null })
const mlRows = (rows, id) => rows.filter(r => r.ml?.[id] && (r.ml[id].quantity !== null || r.ml[id].presence !== null)).map(r => ({ ...r, predicted: r.ml[id], confusion: r.ml[id].confusion }))
function topk(rows, id, k, mode) {
  if (mode !== 'private') return { k, status: 'private_only_selection_bias', positives: null, hits: null, recall: null, onset_events: null, onset_hits: null, onset_recall: null, flagged: null, precision: null }
  const v = rows.filter(r => r.availability_status === 'available' && r.ml?.[id]?.presence !== null && r.ml?.[id]?.presence !== undefined)
  const positives = v.filter(r => r.observed.presence).length, hits = v.filter(r => r.observed.presence && r.ml[id].presence).length
  const onset = v.filter(r => r.observed.presence && r.ml[id].onset_eligible), flagged = v.filter(r => r.ml[id].presence).length
  const onsetHits = onset.filter(r => r.ml[id].presence).length
  return { k, status: 'all_comparable', positives, hits, recall: positives ? hits / positives : null, onset_events: onset.length, onset_hits: onsetHits,
    onset_recall: onset.length ? onsetHits / onset.length : null, flagged, precision: flagged ? hits / flagged : null }
}
export function mlSummary(rows, mode) {
  return Object.fromEntries(candidates.map(c => {
    const m = summary(mlRows(rows, c.id)); m.presence.n = mlRows(rows, c.id).length; m.presence.calibration = []
    if (c.capability === 'presence') m.totals.predicted = null
    if (c.decision_rule.type === 'top_k') m.topk = topk(rows, c.id, c.decision_rule.k, mode)
    return [c.id, m]
  }))
}
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
  result.ml = Object.fromEntries(candidates.map(c => [c.id, { ...c, ...(doc.target_year === 2024
    ? { availability_status: 'available', model_version: 'FICTIONAL', fit_last_target_end: doc.fit_last_target_end, features: ['FICTIONAL_temperature_origin', 'FICTIONAL_city_count_origin'], artifact_sha256: 'f'.repeat(64), reason: null }
    : { availability_status: 'not_available', reason: 'FICTIONAL_missing_saved_prediction' }) }]))
  // Fictional top-k ranks: radio order, computed before protection (like the offline bundle).
  const ranks = new Map(doc.rows.filter(r => r.common_mask).map((r, i) => [r.radio_id, i + 1]))
  for (const r of result.rows) {
    const available = doc.target_year === 2024 && r.availability_status === 'available'
    const outcome = p => { const y = r.observed.presence; return p && y ? 'TP' : p ? 'FP' : y ? 'FN' : 'TN' }
    const rank = ranks.get(r.radio_id), inTop = Number(rank <= 10)
    r.ml = Object.fromEntries(candidates.map(c => [c.id, empty()]))
    if (available) {
      Object.assign(r.ml.rf_A_epi_climate, { presence: r.predicted.presence, presence_score: r.predicted.presence_score, presence_threshold: r.presence_threshold, confusion: r.confusion })
      Object.assign(r.ml.rf_v2_city_propensity, { presence: inTop, presence_score: 1 - rank / 1000, topk_rank: rank, onset_eligible: r.baseline.quantity === 0, confusion: outcome(inTop) })
      for (const [id, shift] of [['residual_h1', .25], ['residual_v2', .5]]) Object.assign(r.ml[id], { quantity: r.predicted.quantity + shift, difference: r.difference + shift, absolute_error: Math.abs(r.difference + shift) })
    }
    r.ml_availability = Object.fromEntries(candidates.map(c => [c.id, available ? 'available' : r.availability_status === 'privacy_suppressed' ? 'privacy_suppressed' : 'not_available']))
  }
  result.ml_metrics = mlSummary(result.rows, mode)
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
    method_labels: { presence: 'FICTIONAL seasonal label', quantity: 'FICTIONAL latest label' },
    experimental_candidates: candidates.map(c => ({ ...c, features: ['FICTIONAL_temperature_origin'] })), default_candidates: defaults }
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
        ml_predicted: Object.fromEntries(Object.entries(mlSummary(rows, mode)).map(([id, m]) => [id, m.totals.predicted])), ml_metrics: mlSummary(rows, mode) }
    })
    return { ...previous, module_version: catalog.module_version, start, end, selected_radio: radio, series, metrics: summary(all), ml_metrics: mlSummary(all, mode),
      by_year: Object.fromEntries(Object.entries(byYear).map(([y, rows]) => [y, summary(rows)])),
      ml_by_year: Object.fromEntries(Object.entries(byYear).map(([y, rows]) => [y, mlSummary(rows, mode)])), disclosure: { mode } }
  }
  throw new Error('Unknown final fictional endpoint')
}
