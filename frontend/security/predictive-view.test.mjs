import { test } from 'node:test'
import assert from 'node:assert/strict'
import { finalFixtureResponse } from './predictive.fixture.mjs'
import { validateBacktestCatalog, validateBacktestHistory, validateBacktestMetadata, validateBacktestWeek } from '../src/services/backtestContract.mjs'
import {
  candidatesFor, cellCategory, decisionText, featureGroups, formatPlain, GLOBAL_VERDICTS, globalVerdict, legendItems, METHOD_HELP, methodSources, mostActiveWeek,
  PROTECTED_EMPTY, PROTECTED_NOTE, readUrlState, selectedCandidate, summaryCards, writeUrlState,
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
  const c = result.ml_metrics[primary.method].presence.confusion
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
  const state = readUrlState(new URLSearchParams('anio=2024&se=15&vista=cuantos&metodo=comparar&modelo=residual_h1&radio=999000001&disclosure=private&modo=privado'))
  assert.deepEqual(state, { year: 2024, week: 15, view: 'quantity', method: 'compare', layer: 'expected', radio: '999000001', model: 'residual_h1' })
  const written = writeUrlState(state).toString()
  assert.equal(written, 'anio=2024&se=15&vista=cuantos&metodo=comparar&modelo=residual_h1&radio=999000001')
  assert.equal(readUrlState(new URLSearchParams('modelo=../x')).model, '')
  assert.doesNotMatch(written, /disclosure|private|privado/)
  assert.equal(readUrlState(new URLSearchParams('radio=../x&se=99')).radio, '')
  assert.equal(readUrlState(new URLSearchParams('se=99')).week, null)
})

test('model selector is built from metadata: several candidates per question, v2 by default', () => {
  assert.equal(validateBacktestMetadata(metadata, catalog), metadata)
  assert.deepEqual(candidatesFor(metadata, 'presence').map(c => c.id), ['rf_A_epi_climate', 'rf_v2_city_propensity'])
  assert.deepEqual(candidatesFor(metadata, 'quantity').map(c => c.id), ['residual_h1', 'residual_v2'])
  assert.deepEqual(methodSources(metadata, 'presence').map(s => [s.source, s.method]), [['ml', 'rf_v2_city_propensity'], ['reference', 'presence_seasonal']])
  assert.equal(methodSources(metadata, 'quantity')[0].method, 'residual_v2')
  assert.equal(methodSources(metadata, 'presence', 'rf_A_epi_climate')[0].method, 'rf_A_epi_climate')
  // A model of the other question (or an unknown id) falls back to the default of this question.
  assert.equal(selectedCandidate(metadata, 'presence', 'residual_v2'), 'rf_v2_city_propensity')
  assert.equal(selectedCandidate(metadata, 'quantity', 'FICTIONAL_unknown'), 'residual_v2')
  const future = { ...metadata, experimental_candidates: [{ ...metadata.experimental_candidates[3], id: 'fictional_residual_next' }], default_candidates: { quantity: 'fictional_residual_next' } }
  assert.equal(methodSources(future, 'quantity')[0].method, 'fictional_residual_next')
  assert.equal(globalVerdict(future, 'fictional_residual_next'), null)
  assert.deepEqual(methodSources({ ...metadata, experimental_candidates: undefined }, 'presence').map(s => s.source), ['reference'])
  assert.throws(() => validateBacktestMetadata({ ...metadata, experimental_candidates: [{ ...metadata.experimental_candidates[2], promotion: { decision: 'promoted' } }] }, catalog))
  assert.throws(() => validateBacktestMetadata({ ...metadata, default_candidates: { presence: 'residual_v2' } }, catalog))
})

test('fixed verdicts per candidate and plain-language decision rules', () => {
  const rf = globalVerdict(metadata, 'rf_v2_city_propensity').text.join(' ')
  assert.match(rf, /recall@10 0,160 frente a 0,156; diferencia no significativa\)\. Mejor que los modelos anteriores\./)
  const residual = globalVerdict(metadata, 'residual_v2').text.join(' ')
  assert.match(residual, /Error promedio 13,6 % menor que repetir la semana anterior en 2021–2023 \(diferencia con intervalo de confianza que excluye 0\)\. Subestima semanas de muchos casos\./)
  for (const text of [rf, residual]) assert.match(text, /2024 es una comparación ya observada; ningún modelo está aprobado para uso operativo\./)
  assert.ok(globalVerdict(metadata, 'rf_A_epi_climate').text.length > 0)
  assert.ok(GLOBAL_VERDICTS.every(v => v.source.length > 0))
  assert.equal(decisionText(metadata.experimental_candidates[2]), 'Marca los 10 radios con mayor prioridad cada semana.')
  assert.match(METHOD_HELP.rf_v2_city_propensity, /Marca los 10 radios con mayor prioridad cada semana/)
})

test('top-k recall is delivered only in private mode; protected mode keeps the selection-bias rule', () => {
  const exact = week(2024, 15, 'private'), safe = week(2024, 15, 'presentation')
  const topk = exact.ml_metrics.rf_v2_city_propensity.topk
  assert.equal(topk.status, 'all_comparable'); assert.equal(topk.flagged, 10); assert.ok(topk.recall !== null)
  assert.equal(exact.rows.filter(r => r.ml.rf_v2_city_propensity.presence === 1).length, 10)
  assert.equal(safe.ml_metrics.rf_v2_city_propensity.topk.status, 'private_only_selection_bias')
  assert.equal(safe.ml_metrics.rf_v2_city_propensity.topk.recall, null)
  const leaked = structuredClone(safe); leaked.ml_metrics.rf_v2_city_propensity.topk.recall = .5
  assert.throws(() => validateBacktestWeek(leaked, catalog, find(2024, 15), 'presentation'))
  const list = catalog.weeks.filter(w => w.target_year === 2024)
  const history = validateBacktestHistory(api(`/history?start=${list[0].target_week}&end=${list.at(-1).target_week}&disclosure=presentation`), catalog, list[0].target_week, list.at(-1).target_week, '', 'presentation')
  assert.equal(history.ml_by_year['2024'].rf_v2_city_propensity.topk.recall, null)
  assert.ok(typeof history.series[0].ml_predicted === 'object')
})

test('model inputs are described as families without values', () => {
  assert.deepEqual(featureGroups(['count_lag_1', 'neighbor_count_mean', 'temperature_origin', 'seno', 'superficie_km2', 'presence_lag_2']),
    ['Historia reciente de registros del radio', 'Actividad reciente de los radios vecinos', 'Clima de la ciudad (un único punto de referencia)', 'Época del año', 'Características fijas del radio (superficie, vecinos)'])
})
