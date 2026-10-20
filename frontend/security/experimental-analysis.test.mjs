import { test } from 'node:test'
import assert from 'node:assert/strict'
import { metricDefinitions, validateEvaluation, validateHistory, scoreSegments, formatScore } from '../src/services/experimentalAnalysis.mjs'

const schema = 'sigard-retrospective-spatial-score/1'
const versions = { A: ['spatial_rf_05c_v1', 'official-spatial-rf-research-0.5c.0'], B: ['spatial_rf_B_05f_v1', 'official-spatial-rf-B-research-0.5f.0'] }
const starts = [...Array(8)].map((_, i) => 7 + i * 7).concat([...Array(8)].map((_, i) => 70 + i * 7), [...Array(4)].map((_, i) => 133 + i * 7))
const weeks = starts.map((day, i) => ({ target_week_start: new Date(Date.UTC(2024, 0, day)).toISOString().slice(0, 10),
  target_week_end: new Date(Date.UTC(2024, 0, day + 6)).toISOString().slice(0, 10), target_epidemiological_year: 2024, target_epidemiological_week: Math.floor(day / 7) + 1,
  evaluation_partition: i < 8 ? 'train' : i < 16 ? 'validation' : 'test' }))
const models = ['A', 'B'].map(id => ({ model_id: id, experiment_id: versions[id][0], training_version: versions[id][1], weeks }))
const catalog = { schema_version: schema, models }
function evaluation() {
  return { schema_version: 'sigard-retrospective-spatial-evaluation/1', calendar_version: 'ar-snvs-2020-2026-v1', coverage_scenario: 'spatial_assumed_2024_v1',
    coverage_verified: false, retrospective: true, previously_examined: true, operational_use_authorized: false, publication_authorized: false,
    evaluation_source: 'frozen_comparative_evaluation', threshold: .5, interpretation_limitations: Array(10).fill('fictional'),
    partitions: ['train', 'validation', 'test'].map(partition => { const subset = weeks.filter(w => w.evaluation_partition === partition); return {
      partition, target_week_start: subset[0].target_week_start, target_week_end: subset.at(-1).target_week_end, week_count: subset.length, evaluated_radio_weeks: 100,
      models: models.map(({ weeks: _weeks, ...model }) => ({ ...model, metrics: Object.fromEntries(metricDefinitions.map(metric => [metric.key, model.model_id === 'A' ? .2 : .4])) })),
    } }) }
}
function history() {
  return { schema_version: schema, radio_censal: '000001', comparisons: weeks.map(w => ({ schema_version: schema, radio_censal: '000001', target_week_start: w.target_week_start, comparable: true,
    results: models.map(model => ({ schema_version: schema, model_id: model.model_id, experiment_id: model.experiment_id, training_version: model.training_version,
      ...w, calendar_version: 'ar-snvs-2020-2026-v1', territory_version: 'capital-census-2022-public-v1', data_kind: 'official_experimental_retrospective',
      score_semantics: 'raw_class_1_score_uncalibrated', coverage_scenario: 'spatial_assumed_2024_v1', coverage_verified: false, retrospective: true,
      previously_examined: true, operational_use_authorized: false, publication_authorized: false, interpretation_limitations: Array(10).fill('fictional'),
      rows: [{ radio_censal: '000001', experimental_score: .2, score_status: 'available', score_unavailable_reason: null,
        data_availability: { prediction_as_of: null, operational_availability: 'not_accredited' } }],
    })) })) }
}

test('evaluation preserves frozen values and undefined metrics; no new results', () => {
  const value = evaluation(); value.partitions[0].models[0].metrics.precision = null
  const before = structuredClone(value)
  assert.equal(validateEvaluation(value, catalog), value)
  assert.deepEqual(value, before)
  assert.equal(formatScore(null), 'No disponible')
  assert.equal(formatScore(0), '0,000')
  assert.equal(metricDefinitions.find(m => m.key === 'brier').direction, 'Menor es mejor')
})

test('evaluation rejects wrong scope, scores as metrics, extras and nonfinite numbers', () => {
  for (const mutate of [v => v.publication_authorized = true, v => v.threshold = .7,
    v => v.partitions[0].models[0].training_version = 'other', v => v.partitions[0].models[0].metrics.roc_auc = NaN,
    v => v.partitions[0].models[0].metrics.brier = -1, v => v.partitions[0].models[0].metrics.brier = null,
    v => v.partitions[0].target_week_start = weeks[1].target_week_start, v => v.partitions[0].patient = 'fictional',
    v => v.partitions[0].models[0].metrics.case_count = 4, v => v.partitions[0].evaluated_radio_weeks = 999999]) {
    const value = evaluation(); mutate(value); assert.throws(() => validateEvaluation(value, catalog))
  }
})

test('history is limited to exactly the selected radio and catalog weeks', () => {
  const value = history(); assert.equal(validateHistory(value, catalog, '000001'), value)
  assert.throws(() => validateHistory(value, catalog, '000002'))
  value.comparisons.pop(); assert.throws(() => validateHistory(value, catalog, '000001'))
})

test('chart breaks on missing scores and purged weeks, preserving real zeros', () => {
  const value = history()
  value.comparisons[0].results[0].rows[0].experimental_score = 0
  value.comparisons[2].results[0].rows[0] = { ...value.comparisons[2].results[0].rows[0], experimental_score: null, score_status: 'not_computed', score_unavailable_reason: 'frozen_score_missing' }
  value.comparisons[2].comparable = false
  validateHistory(value, catalog, '000001')
  const segments = scoreSegments(value.comparisons, 'A')
  assert.equal(segments.length, 4)
  assert.equal(segments[0][0].score, 0)
  assert.ok(segments.every(segment => segment.every((p, i) => !i || p.time - segment[i - 1].time === 7 * 86400000)))
  assert.equal(segments.flat().length, 19)
})

test('actual charts render accessible values, metric explanations and scientific limits', async () => {
  const { readFile } = await import('node:fs/promises')
  const { transformWithOxc } = await import('vite')
  const React = await import('react')
  const { renderToStaticMarkup } = await import('react-dom/server')
  const url = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
  const replacements = { react: new URL('../node_modules/react/index.js', import.meta.url).href,
    'react/jsx-runtime': new URL('../node_modules/react/jsx-runtime.js', import.meta.url).href,
    '../services/experimentalResults': url('export const researchEvaluation=()=>{},researchHistory=()=>{};'),
    '../services/experimentalAnalysis.mjs': new URL('../src/services/experimentalAnalysis.mjs', import.meta.url).href }
  const source = await readFile(new URL('../src/components/ExperimentalAnalysis.jsx', import.meta.url), 'utf8')
  const transformed = await transformWithOxc(source, 'ExperimentalAnalysis.jsx', { jsx: { runtime: 'automatic' } })
  const code = transformed.code.replace(/(['"])([^'"]+)\1/g, (original, quote, value) => replacements[value] ? JSON.stringify(replacements[value]) : original)
  const { EvaluationComparison, RadioTimeline } = await import(url(code))
  const metrics = renderToStaticMarkup(React.createElement(EvaluationComparison, { evaluation: evaluation(), partition: 'test', onPartitionChange() {} }))
  const temporal = renderToStaticMarkup(React.createElement(RadioTimeline, { history: history(), week: weeks[0].target_week_start }))
  assert.ok(metrics.includes('Qué representa') && metrics.includes('Brier') && metrics.includes('Ninguna métrica por sí sola establece superioridad'))
  assert.ok(metrics.includes('width:20%') && metrics.includes('width:40%'))
  assert.ok(temporal.includes('role="img"') && temporal.includes('Consultar valores por semana'))
  assert.ok(temporal.includes('incluidas las purgadas') && !temporal.includes('NaN'))
})
