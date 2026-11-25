// Internal alerts (module 4): wording and client-side checks. Values arrive already
// protected by the API ("protegido" below 5); this module never computes metrics.
import { METHOD_NAMES } from './predictiveView.mjs'

export const PROTECTED = 'protegido'
export const MINIMUM_COUNT = 5
export const PREVIEW_LABEL = 'Frecuencia de activación en 2021–2024 (reconstrucción retrospectiva; 2024 ya observado)'
export const CHANNEL_NOTE = 'Avisos internos del panel de administración: cada candidata requiere la revisión de un administrador y la publicación ciudadana está bloqueada.'
export const PERIODICITY_NOTE = 'El administrador ejecuta la evaluación al recibir la entrega semanal de datos; la automatización queda fuera del alcance del prototipo.'
export const RETROSPECTIVE_NOTE = 'Reconstrucción retrospectiva 2021–2024 con predicciones ya integradas; 2024 ya fue observado. No es un sistema operativo.'

export const FLOW_STEPS = [
  ['Regla', 'Un administrador define radios, pregunta, modelo, umbral y semanas consecutivas.'],
  ['Evaluación semanal', 'Al recibir la entrega semanal, el administrador elige la semana y ejecuta la evaluación.'],
  ['Alerta candidata', 'Sólo si la condición se cumple en todas las semanas exigidas y con predicciones disponibles.'],
  ['Revisión humana', 'Un administrador aprueba con comentario o descarta con motivo.'],
  ['Aviso interno aprobado', 'Queda registrado en el historial. No se envían correos, SMS ni publicaciones a la ciudadanía.'],
]

export const STATUS_LABELS = { pending: 'Pendiente de revisión', approved_internal: 'Aviso interno aprobado', discarded: 'Descartada' }
export const REASON_LABELS = {
  false_alarm: 'Probable falsa alarma', insufficient_context: 'Contexto insuficiente', duplicate: 'Duplicada', other: 'Otro motivo',
}
export const CAPABILITY_LABELS = { presence: '¿Dónde?', quantity: '¿Cuántos?' }
export const ACTION_LABELS = {
  rule_created: 'Regla creada', rule_updated: 'Regla editada', evaluation_run: 'Evaluación ejecutada',
  evaluation_no_data: 'Evaluación sin datos', candidate_approved: 'Candidata aprobada', candidate_discarded: 'Candidata descartada',
  citizen_publication_blocked: 'Intento de publicación ciudadana bloqueado', candidates_exported: 'Exportación de candidatas',
}
const MODEL_LABELS = { ...METHOD_NAMES, count_latest: 'Método de referencia: repetir la semana anterior' }

export const modelName = id => MODEL_LABELS[id] || id
export const formatValue = value => value === null || value === undefined ? 'sin dato' : value === PROTECTED ? 'protegido' : String(value).replace('.', ',')

export function formatWeek(iso) {
  if (!iso) return ''
  const [year, month, day] = iso.split('-')
  return `${day}/${month}/${year}`
}

export function ruleSummary(rule, k) {
  const scope = rule.radio_ids?.length ? `${rule.radio_ids.length} radio${rule.radio_ids.length === 1 ? '' : 's'}` : 'todo el territorio común'
  const condition = rule.capability === 'presence'
    ? `entre los ${k ?? rule.k ?? 10} radios con mayor prioridad`
    : `${formatValue(rule.threshold)} o más registros esperados`
  const weeks = rule.consecutive_weeks === 1 ? 'en la semana evaluada' : `durante ${rule.consecutive_weeks} semanas consecutivas`
  return `${CAPABILITY_LABELS[rule.capability]} ${condition} ${weeks} · ${scope} · ${modelName(rule.model)}`
}

export function modelsFor(status, capability) {
  return (status?.models || []).filter(model => model.capability === capability)
}

// Client-side mirror of the API checks; the API remains authoritative.
export function validateRuleForm(form, status) {
  const errors = {}
  if (form.name.trim().length < 3) errors.name = 'Usá al menos 3 caracteres.'
  if (!modelsFor(status, form.capability).some(model => model.id === form.model)) errors.model = 'Elegí un modelo disponible para esta pregunta.'
  if (form.capability === 'quantity') {
    const value = Number(String(form.threshold).replace(',', '.'))
    if (String(form.threshold).trim() === '' || !Number.isFinite(value) || value < MINIMUM_COUNT || value > 1000) {
      errors.threshold = `El umbral debe estar entre ${MINIMUM_COUNT} y 1000 registros esperados (protección de celdas pequeñas).`
    }
  }
  if (form.scope === 'selected' && !form.radio_ids.length) errors.radio_ids = 'Elegí al menos un radio.'
  const weeks = Number(form.consecutive_weeks)
  if (!Number.isInteger(weeks) || weeks < 1 || weeks > 4) errors.consecutive_weeks = 'Entre 1 y 4 semanas.'
  return errors
}

export function rulePayload(form) {
  return {
    name: form.name.trim(), capability: form.capability, model: form.model,
    radio_ids: form.scope === 'selected' ? [...form.radio_ids] : null,
    threshold: form.capability === 'quantity' ? Number(String(form.threshold).replace(',', '.')) : null,
    consecutive_weeks: Number(form.consecutive_weeks), enabled: Boolean(form.enabled),
  }
}

export function previewText(preview) {
  if (!preview) return ''
  const records = preview.with_observed_records === PROTECTED
    ? 'la cantidad con registros observados está protegida (menos de 5 o complemento menor a 5)'
    : `${preview.with_observed_records} con registros observados en esa semana`
  return `Se habría activado ${preview.activations} ${preview.activations === 1 ? 'vez' : 'veces'} en ${preview.weeks_with_activation} de ${preview.evaluable_weeks} semanas evaluables; ${records}.`
}

// «1 candidata nueva» / «0 o 2 candidatas nuevas»: the count with its noun in singular or plural (F7a).
export function countText(count, singular, plural) {
  return `${count} ${count === 1 ? singular : plural}`
}

export function evaluationText(summary) {
  const rules = summary?.rules || []
  const active = rules.filter(rule => rule.enabled)
  const insufficient = active.reduce((total, rule) => total + (rule.insufficient_data || 0), 0)
  return `${countText(summary?.created ?? 0, 'candidata nueva', 'candidatas nuevas')} · ${countText(active.length, 'regla activa evaluada', 'reglas activas evaluadas')} · ${countText(rules.length - active.length, 'inactiva', 'inactivas')}`
    + (insufficient ? ` · ${countText(insufficient, 'radio', 'radios')} sin predicciones suficientes (no generan candidatas)` : '')
}
