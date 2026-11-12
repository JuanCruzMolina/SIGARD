// Entirely generated UI transport fixture, never used by offline compilation or project metrics.
export const context = { schema_version: 'sigard-historical-backtest/1', dataset_version: 'FICTIONAL-DATA', campaign_version: 'FICTIONAL-CAMPAIGN', data_policy_version: 'FICTIONAL-POLICY', territory_version: 'FICTIONAL-GRID' }
const starts = ['2019-12-29', '2021-01-03', '2022-01-02', '2023-01-01', '2023-12-31', '2024-12-29', '2026-01-04']
const lengths = [53, 52, 52, 52, 52, 53, 52]
export const ids = Array.from({ length: 263 }, (_, i) => `999${String(i).padStart(6, '0')}`)
const add = (value, n) => new Date(Date.parse(value) + n * 86400000).toISOString().slice(0, 10)
const weeks = starts.flatMap((start, i) => Array.from({ length: lengths[i] }, (_, n) => ({
  target_year: 2020 + i, target_epi_week: n + 1, target_week: add(start, n * 7), target_end: add(start, n * 7 + 6),
  origin_week: add(start, n * 7 - 7), origin_end: add(start, n * 7 - 1), availability_status: i === 0 ? 'insufficient_training_support' : i < 5 ? 'available' : 'outside_coverage', unavailable_reason: i === 0 ? 'FICTIONAL warmup' : i < 5 ? null : 'FICTIONAL outside',
})))
export const catalog = { ...context, calendar_version: 'ar-snvs-2020-2026-v1', radio_ids: ids, weeks }
export const geometry = { type: 'FeatureCollection', features: ids.map((radio_id, i) => {
  const x = 10 + i % 20 / 100, y = 10 + Math.floor(i / 20) / 100
  return { type: 'Feature', properties: { radio_id, common_mask: i < 256 }, geometry: { type: 'Polygon', coordinates: [[[x, y], [x + .009, y], [x + .009, y + .009], [x, y + .009], [x, y]]] } }
}) }
export const metadata = { ...context, evaluation_type: 'event_time_retrospective_reconstruction', horizon_weeks: 1, selected_methods: { presence: 'presence_seasonal', quantity: 'count_latest' }, operational_enabled: false, alerts_enabled: false, reference_is_not_trained_ml: true }
export function summary(rows) {
  const valid = rows.filter(r => r.availability_status === 'available'); const n = valid.length
  const total = key => n ? valid.reduce((sum, r) => sum + r[key].quantity, 0) : null
  const errors = valid.map(r => r.difference); const mae = n ? errors.reduce((s, e) => s + Math.abs(e), 0) / n : null
  const quantity = { n, mae, rmse: n ? Math.sqrt(errors.reduce((s, e) => s + e * e, 0) / n) : null, bias: n ? errors.reduce((s, e) => s + e, 0) / n : null }
  const confusion = Object.fromEntries(['TP', 'FP', 'FN', 'TN'].map(code => [code, valid.filter(r => r.confusion === code).length]))
  return { n_comparable: n, totals: { predicted: total('predicted'), observed: total('observed'), baseline: total('baseline') }, quantity, baseline: quantity, quantity_zero: quantity, quantity_positive: quantity,
    presence: { confusion, brier: n ? .12 : null, average_precision: n ? .4 : null, roc_auc: n ? .6 : null, precision: n ? .5 : null, recall: n ? .5 : null, f1: n ? .5 : null } }
}
export function comparison(w) {
  const covered = w.target_year <= 2024
  const rows = ids.map((radio_id, i) => {
    const common = i < 256, available = common && w.availability_status === 'available'
    const y = covered && !(w.target_year === 2024 && w.target_epi_week > 24) && i === 0 ? 1 : 0
    const p = i < 2 ? 1 : 0; const difference = available ? .75 - y : null
    return { radio_id, common_mask: common, availability_status: covered && !common ? 'outside_common_territory' : w.availability_status,
      territorial_quality: y ? 'approximate' : 'no_assigned_record', coverage_status: covered ? y ? 'covered_observed' : 'covered_assumed_zero' : 'out_of_coverage', zero_provenance: covered && !y ? 'project_owner_declared_coverage_2020_2024' : null,
      predicted: { presence_score: available ? p ? .7 : .1 : null, presence: available ? p : null, quantity: available ? .75 : null },
      observed: { presence: covered && common ? y : null, quantity: covered && common ? y : null, assigned_records: covered ? y : null }, baseline: { quantity: available ? .75 : null }, presence_threshold: available ? .5 : null,
      confusion: available ? p && y ? 'TP' : p ? 'FP' : y ? 'FN' : 'TN' : null, difference, absolute_error: difference === null ? null : Math.abs(difference) }
  })
  return { ...context, ...w, evaluation_type: 'event_time_retrospective_reconstruction', fit_last_target_end: add(w.origin_week, -42),
    model_version: { presence: 'FICTIONAL/presence', quantity: 'FICTIONAL/count' }, rows, metrics: summary(rows),
    department: { observed_total: covered ? rows[0].observed.quantity : null, assigned_common_total: covered ? rows[0].observed.quantity : null, assigned_masked_total: covered ? 0 : null, unassigned_total: covered ? 0 : null, reconciled: covered ? true : null } }
}
export function fixtureResponse(path) {
  const url = new URL(path, 'http://127.0.0.1:8765'); const name = url.pathname.split('/').at(-1)
  if (name === 'calendar') return catalog
  if (name === 'geometry') return geometry
  if (name === 'metadata') return metadata
  if (name === 'comparison') return comparison(weeks.find(w => w.target_year === Number(url.searchParams.get('year')) && w.target_epi_week === Number(url.searchParams.get('week'))))
  if (name === 'history') {
    const start = url.searchParams.get('start'), end = url.searchParams.get('end'), radio = url.searchParams.get('radio')
    const selected = weeks.filter(w => w.target_week >= start && w.target_week <= end)
    const series = selected.map(w => {
      const result = comparison(w); const rows = result.rows.filter(r => !radio || r.radio_id === radio); const metrics = summary(rows)
      const observed = rows.filter(r => r.common_mask).map(r => r.observed.quantity)
      return { ...w, observed: observed.length && observed.every(v => v !== null) ? observed.reduce((a, b) => a + b, 0) : null, predicted: metrics.totals.predicted, baseline: metrics.totals.baseline, metrics, n_comparable: metrics.n_comparable }
    })
    const rows = selected.flatMap(w => comparison(w).rows.filter(r => !radio || r.radio_id === radio))
    return { ...context, start, end, selected_radio: radio, series, metrics: summary(rows), by_year: Object.fromEntries([...new Set(selected.map(w => w.target_year))].map(year => [year, summary(selected.filter(w => w.target_year === year).flatMap(w => comparison(w).rows.filter(r => !radio || r.radio_id === radio)))])) }
  }
  throw new Error('Unknown fictional endpoint')
}
