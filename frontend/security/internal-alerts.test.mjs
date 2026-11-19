// Internal alerts wording and client checks (module 4). Generated fictional values only.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import {
  CHANNEL_NOTE, PERIODICITY_NOTE, PREVIEW_LABEL, PROTECTED, formatValue, modelName, previewText, rulePayload,
  ruleSummary, validateRuleForm,
} from '../src/services/internalAlerts.mjs'

const status = { radio_ids: ['FX0000001'], models: [
  { id: 'rf_v2_city_propensity', capability: 'presence', rule: { type: 'top_k', k: 3 } },
  { id: 'residual_v2', capability: 'quantity', rule: { type: 'count_estimate' } },
  { id: 'count_latest', capability: 'quantity', reference: true }] }
const form = { name: 'Regla ficticia', capability: 'quantity', model: 'residual_v2', threshold: '5', scope: 'all', radio_ids: [], consecutive_weeks: 2, enabled: true }

test('protected values are always rendered as "protegido"', () => {
  assert.equal(formatValue(PROTECTED), 'protegido')
  assert.equal(formatValue(null), 'sin dato')
  assert.equal(formatValue(7.5), '7,5')
})

test('threshold below 5 and invalid rules are rejected client-side', () => {
  assert.deepEqual(validateRuleForm(form, status), {})
  assert.match(validateRuleForm({ ...form, threshold: '4,9' }, status).threshold, /entre 5 y 1000/)
  assert.ok(validateRuleForm({ ...form, threshold: '' }, status).threshold)
  assert.ok(validateRuleForm({ ...form, model: 'rf_v2_city_propensity' }, status).model)
  assert.ok(validateRuleForm({ ...form, scope: 'selected' }, status).radio_ids)
  assert.ok(validateRuleForm({ ...form, consecutive_weeks: 5 }, status).consecutive_weeks)
  assert.deepEqual(validateRuleForm({ ...form, capability: 'presence', model: 'rf_v2_city_propensity', threshold: '' }, status), {})
})

test('payload sends no threshold for ¿Dónde? and null radios for the whole territory', () => {
  assert.deepEqual(rulePayload({ ...form, capability: 'presence', model: 'rf_v2_city_propensity' }),
    { name: 'Regla ficticia', capability: 'presence', model: 'rf_v2_city_propensity', radio_ids: null, threshold: null, consecutive_weeks: 2, enabled: true })
  assert.equal(rulePayload({ ...form, threshold: '7,5' }).threshold, 7.5)
  assert.deepEqual(rulePayload({ ...form, scope: 'selected', radio_ids: ['FX0000001'] }).radio_ids, ['FX0000001'])
})

test('summaries, preview label and policy texts', () => {
  assert.match(ruleSummary({ ...rulePayload(form), radio_ids: null }), /¿Cuántos\? 5 o más registros esperados durante 2 semanas consecutivas · todo el territorio común/)
  assert.match(ruleSummary({ capability: 'presence', model: 'rf_v2_city_propensity', consecutive_weeks: 1, radio_ids: ['FX0000001'] }, 3), /entre los 3 radios con mayor prioridad en la semana evaluada · 1 radio/)
  assert.equal(modelName('count_latest'), 'Método de referencia: repetir la semana anterior')
  assert.equal(PREVIEW_LABEL, 'Frecuencia de activación en 2021–2024 (reconstrucción retrospectiva; 2024 ya observado)')
  assert.match(previewText({ activations: 14, weeks_with_activation: 14, evaluable_weeks: 29, with_observed_records: PROTECTED }), /14 veces en 14 de 29 semanas.*protegida/)
  assert.match(CHANNEL_NOTE, /revisión de un administrador y la publicación ciudadana está bloqueada/)
  assert.equal(PERIODICITY_NOTE, 'El administrador ejecuta la evaluación al recibir la entrega semanal de datos; la automatización queda fuera del alcance del prototipo.')
})

test('the interface never calls the citizen publication route', async () => {
  const sources = await Promise.all(['../src/components/AdminAlerts.jsx', '../src/services/citizenReports.js']
    .map(path => readFile(new URL(path, import.meta.url), 'utf8')))
  assert.ok(sources.every(source => !/\/publish/.test(source)))
  // The allow-list of alert paths admits approve/discard only.
  const allowList = new RegExp(sources[1].match(/const ALERT_PATHS = \/(.+)\/\r?$/m)[1])
  assert.ok(allowList.test('/candidates/1/approve') && allowList.test('/candidates/2/discard'))
  assert.ok(!allowList.test('/candidates/1/publish') && !allowList.test('/candidates/export.csv'))
})
