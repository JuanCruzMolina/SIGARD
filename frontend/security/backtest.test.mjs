import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { experimentalView, formatValue, lineSegments, validateBacktestCatalog, validateBacktestGeometry, validateBacktestHistory, validateBacktestMetadata, validateBacktestWeek } from '../src/services/backtestContract.mjs'

// Generated contract-only fixture. No project observations or cartography.
const context = { schema_version: 'sigard-historical-backtest/1', dataset_version: 'FICTIONAL', campaign_version: 'FICTIONAL', data_policy_version: 'FICTIONAL-2022', territory_version: 'FICTIONAL' }
const radio_ids = Array.from({ length: 263 }, (_, i) => `999${String(i).padStart(6, '0')}`)
const weeks = [
  { target_year: 2020, target_epi_week: 53, target_week: '2020-12-27', target_end: '2021-01-02', origin_week: '2020-12-20', origin_end: '2020-12-26', availability_status: 'insufficient_training_support' },
  { target_year: 2021, target_epi_week: 1, target_week: '2021-01-03', target_end: '2021-01-09', origin_week: '2020-12-27', origin_end: '2021-01-02', availability_status: 'available' },
]
const catalog = { ...context, calendar_version: 'ar-snvs-2020-2026-v1', weeks, radio_ids }
function result() {
  return { ...context, ...weeks[1], fit_last_target_end: '2020-11-21', metrics: { n_comparable: 256 }, rows: radio_ids.map((radio_id, i) => ({
    radio_id, common_mask: i < 256, availability_status: i < 256 ? 'available' : 'outside_common_territory',
    predicted: { presence: i < 256 ? 1 : null, presence_score: i < 256 ? .7 : null, quantity: i < 256 ? .75 : null },
    observed: { presence: i < 256 ? 0 : null, quantity: i < 256 ? 0 : null }, baseline: { quantity: i < 256 ? .75 : null },
    confusion: i < 256 ? 'FP' : null, presence_threshold: i < 256 ? .5 : null, difference: i < 256 ? .75 : null, absolute_error: i < 256 ? .75 : null,
  })) }
}
test('calendar preserves Argentine 2020 week53 and transition to 2021', () => {
  assert.equal(validateBacktestCatalog(catalog), catalog)
  const bad = structuredClone(catalog); bad.weeks[1].origin_week = '2021-01-03'
  assert.throws(() => validateBacktestCatalog(bad))
  const duplicate = structuredClone(catalog); duplicate.radio_ids[1] = duplicate.radio_ids[0]
  assert.throws(() => validateBacktestCatalog(duplicate))
})
test('exact decimals, zeros and masked unknowns survive validation; temporal or semantic drift blocks', () => {
  const value = result(); assert.equal(validateBacktestWeek(value, catalog, weeks[1]).rows[0].difference, .75)
  assert.equal(value.rows.at(-1).observed.quantity, null)
  for (const mutate of [r => { r.target_week = '2024-01-07' }, r => { r.data_policy_version = 'OLD' }, r => { r.fit_last_target_end = '2021-01-02' }, r => { r.rows[0].observed.quantity = -1 }, r => { r.rows[0].confusion = 'TP' }, r => { r.rows.at(-1).predicted.quantity = 0 }]) {
    const bad = structuredClone(value); mutate(bad); assert.throws(() => validateBacktestWeek(bad, catalog, weeks[1]))
  }
  assert.equal(formatValue(null), 'No disponible'); assert.equal(formatValue(0), '0')
})
test('only selected stage2 references, common polygon universe and offline metadata allowed', () => {
  const metadata = { ...context, evaluation_type: 'event_time_retrospective_reconstruction', horizon_weeks: 1, selected_methods: { presence: 'presence_seasonal', quantity: 'count_latest' }, operational_enabled: false, alerts_enabled: false, reference_is_not_trained_ml: true }
  assert.equal(validateBacktestMetadata(metadata, catalog), metadata)
  assert.throws(() => validateBacktestMetadata({ ...metadata, selected_methods: { presence: 'rf_new', quantity: 'count_latest' } }, catalog))
  const geo = { type: 'FeatureCollection', features: radio_ids.map((radio_id, i) => ({ properties: { radio_id, common_mask: i < 256 }, geometry: { type: 'Polygon' } })) }
  assert.equal(validateBacktestGeometry(geo, catalog), geo)
  geo.features[0].geometry.type = 'Point'; assert.throws(() => validateBacktestGeometry(geo, catalog))
})
test('unknown history creates genuine path breaks and no predictions for unsupported weeks', () => {
  const points = [{ observed: 1 }, { observed: null }, { observed: 0 }, { observed: 2 }]
  assert.deepEqual(lineSegments(points, 'observed', i => i, y => y), ['M0,1', 'M2,0 L3,2'])
  const value = { ...context, start: weeks[0].target_week, end: weeks[1].target_week, selected_radio: null,
    series: weeks.map((w, i) => ({ ...w, observed: 0, predicted: i ? .75 : null, baseline: i ? .75 : null })) }
  assert.equal(validateBacktestHistory(value, catalog, value.start, value.end, ''), value)
  value.series[0].predicted = 0; assert.throws(() => validateBacktestHistory(value, catalog, value.start, value.end, ''))
})
test('service stays loopback/read-only; no clinical/public fixture or HTTP fitting paths', async () => {
  const service = await readFile(new URL('../src/services/backtestResults.js', import.meta.url), 'utf8')
  assert.match(service, /if \(!localResearchEnabled\(\)\)/)
  for (const text of ['http://127.0.0.1:8765/api/v1/research/predictive', "method: 'GET'", "credentials: 'omit'", "cache: 'no-store'", "redirect: 'error'"]) assert.ok(service.includes(text))
  assert.doesNotMatch(service, /\/train|\/fit|localStorage|sessionStorage/)
})

test('presentation rejects leaked small values; exact private response cannot masquerade as protected', () => {
  const value=result();value.module_version='sigard-predictive-experimental/2';value.disclosure={mode:'private'}
  assert.equal(validateBacktestWeek(value,catalog,weeks[1],'private'),value)
  assert.throws(()=>validateBacktestWeek(value,catalog,weeks[1],'presentation'))
  value.disclosure.mode='presentation';value.department={observed_total:null}
  assert.throws(()=>validateBacktestWeek(value,catalog,weeks[1],'presentation'))
})

const blank = () => ({ presence_score: null, presence: null, presence_threshold: null, topk_rank: null, onset_eligible: null, quantity: null, confusion: null, difference: null, absolute_error: null })
const model = (capability, decision_rule) => ({ capability, decision_rule, state: 'experimental_not_promoted', calibrated: false, promotion: { decision: 'not_promoted' }, availability_status: 'available', fit_last_target_end: '2020-11-21' })

test('missing ML never substitutes the reference, and ML decimals remain independent', () => {
  const r = result()
  assert.equal(experimentalView(r, 'ml', 'FICTIONAL_count').rows[0].predicted.quantity, null)
  assert.equal(experimentalView(r, 'reference').rows[0].predicted.quantity, .75)
  r.ml = { FICTIONAL_count: model('quantity', { type: 'count_estimate' }) }
  r.rows[0].ml = { FICTIONAL_count: { ...blank(), quantity: 1.25, difference: 1.25, absolute_error: 1.25 } }
  assert.equal(validateBacktestWeek(r, catalog, weeks[1]), r)
  assert.equal(experimentalView(r, 'ml', 'FICTIONAL_count').rows[0].predicted.quantity, 1.25)
  assert.equal(experimentalView(r, 'ml', 'FICTIONAL_other').rows[0].predicted.quantity, null)
  assert.equal(r.rows[0].predicted.quantity, .75)
  r.rows[0].ml.FICTIONAL_count.difference = 0
  assert.throws(() => validateBacktestWeek(r, catalog, weeks[1]))
})

test('top-k contract: presence follows the rank, never more than k, exactly k when all radios are visible', () => {
  const r = result()
  r.ml = { FICTIONAL_topk: model('presence', { type: 'top_k', k: 10 }) }
  const rank = new Map(r.rows.filter(x => x.common_mask).map((x, i) => [x.radio_id, i + 1]))
  for (const row of r.rows) {
    const k = rank.get(row.radio_id), p = k ? Number(k <= 10) : null, y = row.observed.presence
    row.ml = { FICTIONAL_topk: k && row.availability_status === 'available' ? { ...blank(), presence: p, presence_score: 1 - k / 1000, topk_rank: k, onset_eligible: false, confusion: p && y ? 'TP' : p ? 'FP' : y ? 'FN' : 'TN' } : blank() }
  }
  assert.equal(validateBacktestWeek(r, catalog, weeks[1]), r)
  const changed = structuredClone(r); changed.rows[10].ml.FICTIONAL_topk.presence = 1; changed.rows[10].ml.FICTIONAL_topk.confusion = 'FP'
  assert.throws(() => validateBacktestWeek(changed, catalog, weeks[1]), 'rank 11 cannot be flagged')
  const fewer = structuredClone(r); fewer.ml.FICTIONAL_topk.decision_rule.k = 11
  assert.throws(() => validateBacktestWeek(fewer, catalog, weeks[1]), 'all radios visible requires exactly k')
  const threshold = structuredClone(r); threshold.rows[0].ml.FICTIONAL_topk.presence_threshold = .5
  assert.throws(() => validateBacktestWeek(threshold, catalog, weeks[1]))
  const unknown = structuredClone(r); unknown.rows[0].ml.FICTIONAL_unknown = blank()
  assert.throws(() => validateBacktestWeek(unknown, catalog, weeks[1]))
  const promoted = structuredClone(r); promoted.ml.FICTIONAL_topk.promotion.decision = 'promoted'
  assert.throws(() => validateBacktestWeek(promoted, catalog, weeks[1]))
})

test('future ML adjustment and ML outputs on a protected cell are rejected', () => {
  const r = result()
  r.ml = { presence: { availability_status: 'available', state: 'experimental_evaluated', calibrated: false, fit_last_target_end: '2021-01-02' } }
  assert.throws(() => validateBacktestWeek(r, catalog, weeks[1]))
  delete r.ml
  r.rows.at(-1).ml = { quantity: 1, presence: null, presence_score: null, presence_threshold: null }
  assert.throws(() => validateBacktestWeek(r, catalog, weeks[1]))
})
