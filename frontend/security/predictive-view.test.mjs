import { test } from 'node:test'
import assert from 'node:assert/strict'
import { finalFixtureResponse } from './predictive.fixture.mjs'
import { validateBacktestCatalog, validateBacktestWeek } from '../src/services/backtestContract.mjs'
import {
  cellCategory, featureGroups, formatPlain, globalVerdict, legendItems, methodSources, mostActiveWeek,
  PROTECTED_EMPTY, PROTECTED_NOTE, readUrlState, summaryCards, writeUrlState,
} from '../src/services/predictiveView.mjs'

// Generated fictional transport only; no project observations, cartography or predictions.
const api = path => finalFixtureResponse(`http://127.0.0.1:8765/api/v1/research/predictive${path}`)
const catalog = validateBacktestCatalog(api('/calendar'))
const metadata = api('/metadata')
const find = (year, week) => catalog.weeks.find(w => w.target_year === year && w.target_epi_week === week)
const week = (year, se, mode) => validateBacktestWeek(api(`/comparison?year=${year}&week=${se}&disclosure=${mode}`), catalog, find(year, se), mode)
const text = summary => [summary.title, summary.text, summary.note, ...(summary.cards || []).flatMap(c => [c.label, c.value, c.detail])].filter(Boolean).join(' | ')
const orders = view => { const s = methodSources(metadata, view); return [s, [...s].reverse()] }

test('protected mode never presents precision, false alarms or anticipation as performance', () => {
  const result = week(2024, 15, 'presentation')
  assert.ok(result.metrics.n_comparable > 0)
  for (const view of ['presence', 'quantity']) for (const [primary, other] of orders(view)) {
    const summary = summaryCards({ result, view, primary, other, mode: 'presentation' })
    assert.equal(summary.kind, 'cards')
    assert.equal(summary.note, PROTECTED_NOTE)
    assert.doesNotMatch(text({ ...summary, note: '' }), /precisi|falsa|alarma|anticip|acierto|recall/i)
    for (const card of summary.cards) assert.match(`${card.label} ${card.detail}`, /radios visibles|sin predicción guardada/i)
  }
})

test('private mode shows plain-language performance terms from delivered confusion counts', () => {
  const result = week(2024, 15, 'private')
  const [primary, other] = methodSources(metadata, 'presence')
  const summary = summaryCards({ result, view: 'presence', primary, other, mode: 'private' })
  const all = text(summary)
  assert.match(all, /falsas alarmas/); assert.match(all, /anticipó/); assert.match(all, /Radios priorizados que tuvieron registros/)
  const c = result.ml_metrics.presence.confusion
  assert.equal(summary.cards.find(card => card.id === 'anticipated').value, `${c.TP} de ${c.TP + c.FN}`)
})

test('legend omits categories and ranges impossible in protected mode', () => {
  const protectedLegend = legendItems('presence', 'presentation').map(i => i.key)
  assert.deepEqual(protectedLegend.filter(k => ['FP', 'TN'].includes(k)), [])
  assert.doesNotMatch(legendItems('presence', 'presentation').map(i => i.label).join(' '), /falsa alarma|correctamente sin alerta/i)
  assert.ok(['TP', 'FP', 'FN', 'TN'].every(k => legendItems('presence', 'private').some(i => i.key === k)))
  assert.deepEqual(legendItems('quantity', 'presentation').filter(i => i.key.startsWith('bin-')).map(i => i.label), ['5 a 10', 'Más de 10'])
  assert.equal(legendItems('quantity', 'private').filter(i => i.key.startsWith('bin-')).length, 6)
  for (const mode of ['presentation', 'private']) assert.ok(['protected', 'outside', 'nodata'].every(k => legendItems('presence', mode).some(i => i.key === k)))
})

test('empty weeks collapse into one explanation, never tables of unavailable values', () => {
  const [primary, other] = methodSources(metadata, 'presence')
  const protectedWeek = summaryCards({ result: week(2021, 1, 'presentation'), view: 'presence', primary, other, mode: 'presentation' })
  assert.equal(protectedWeek.kind, 'protected'); assert.equal(protectedWeek.text, PROTECTED_EMPTY); assert.equal(protectedWeek.cards, undefined)
  assert.equal(summaryCards({ result: week(2020, 53, 'presentation'), view: 'presence', primary, other, mode: 'presentation' }).kind, 'unavailable')
  assert.match(summaryCards({ result: week(2025, 1, 'presentation'), view: 'presence', primary, other, mode: 'presentation' }).text, /fuera del período/)
})

test('protected, outside the common universe, no data and real zero stay distinct; hidden is never zero', () => {
  const protectedWeek = week(2024, 15, 'presentation'), privateWeek = week(2024, 15, 'private')
  const categories = new Set(protectedWeek.rows.map(r => cellCategory(r, 'presence')))
  assert.ok(categories.has('protected') && categories.has('outside') && !categories.has('TN') && !categories.has('FP'))
  assert.equal(cellCategory(week(2020, 53, 'private').rows[0], 'presence'), 'nodata')
  assert.ok(privateWeek.rows.some(r => cellCategory(r, 'presence') === 'TN' && r.observed.quantity === 0))
  const hidden = protectedWeek.rows.find(r => r.availability_status === 'privacy_suppressed')
  assert.equal(hidden.observed.quantity, null); assert.equal(formatPlain(hidden.observed.quantity), '—')
})

test('default week is the one with most disclosable radios in the active mode', () => {
  const list = catalog.weeks.filter(w => w.target_year === 2024)
  const history = api(`/history?start=${list[0].target_week}&end=${list.at(-1).target_week}&disclosure=presentation`)
  assert.equal(mostActiveWeek(history.series), find(2024, 15).target_week)
  const tied = [{ availability_status: 'available', n_comparable: 3, observed: 10, target_week: '2024-01-07' }, { availability_status: 'available', n_comparable: 3, observed: 10, target_week: '2024-01-14' }]
  assert.equal(mostActiveWeek(tied), '2024-01-14')
  assert.equal(mostActiveWeek([{ availability_status: 'available', n_comparable: 0, observed: null, target_week: '2021-01-03' }]), null)
})

test('URL keeps week, question, method and radio, but never the disclosure mode', () => {
  const state = readUrlState(new URLSearchParams('anio=2024&se=15&vista=cuantos&metodo=comparar&radio=999000001&disclosure=private&modo=privado'))
  assert.deepEqual(state, { year: 2024, week: 15, view: 'quantity', method: 'compare', layer: 'expected', radio: '999000001' })
  const written = writeUrlState(state).toString()
  assert.equal(written, 'anio=2024&se=15&vista=cuantos&metodo=comparar&radio=999000001')
  assert.doesNotMatch(written, /disclosure|private|privado/)
  assert.equal(readUrlState(new URLSearchParams('radio=../x&se=99')).radio, '')
  assert.equal(readUrlState(new URLSearchParams('se=99')).week, null)
})

test('method selector and verdict are driven by metadata, not component names', () => {
  assert.deepEqual(methodSources(metadata, 'presence').map(s => [s.source, s.method]), [['ml', 'rf_A_epi_climate'], ['reference', 'presence_seasonal']])
  const future = { ...metadata, experimental_methods: { presence: 'FICTIONAL_rf_next', quantity: 'FICTIONAL_residual_next' } }
  assert.equal(methodSources(future, 'quantity')[0].method, 'FICTIONAL_residual_next')
  assert.equal(globalVerdict(future), null)
  assert.ok(globalVerdict(metadata).text.length > 0)
  assert.deepEqual(methodSources({ ...metadata, experimental_methods: undefined }, 'presence').map(s => s.source), ['reference'])
})

test('model inputs are described as families without values', () => {
  assert.deepEqual(featureGroups(['count_lag_1', 'neighbor_count_mean', 'temperature_origin', 'seno', 'superficie_km2', 'presence_lag_2']),
    ['Historia reciente de registros del radio', 'Actividad reciente de los radios vecinos', 'Clima de la ciudad (un único punto de referencia)', 'Época del año', 'Características fijas del radio (superficie, vecinos)'])
})
