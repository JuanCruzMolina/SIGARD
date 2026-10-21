import { validateComparison } from './experimentalContract.mjs'

export const metricDefinitions = [
  { key: 'precision', label: 'Precisión', direction: 'Mayor es mejor', description: 'Entre las predicciones positivas, proporción con etiqueta positiva provisional. Depende del umbral 0,5.' },
  { key: 'recall', label: 'Sensibilidad', direction: 'Mayor es mejor', description: 'Proporción de etiquetas positivas provisionales detectadas con el umbral 0,5.' },
  { key: 'f1', label: 'F1', direction: 'Mayor es mejor', description: 'Media armónica de precisión y sensibilidad; resume su equilibrio con el umbral 0,5.' },
  { key: 'average_precision_pr_auc', label: 'Average Precision', direction: 'Mayor es mejor', description: 'Resumen de la curva precisión–sensibilidad a distintos umbrales. No es el área trapezoidal de esa curva.' },
  { key: 'roc_auc', label: 'ROC-AUC', direction: 'Mayor es mejor', description: 'Capacidad de ordenar etiquetas positivas por encima de negativas. Su valor global puede reflejar diferencias entre semanas.' },
  { key: 'brier', label: 'Brier', direction: 'Menor es mejor', description: 'Error cuadrático medio entre score y etiqueta experimental. Un valor bajo no acredita calibración clínica.' },
]

export const partitionNames = { train: 'Entrenamiento', validation: 'Validación ya examinada', test: 'Prueba ya examinada' }
export const formatScore = value => value === null || value === undefined ? 'No disponible' : new Intl.NumberFormat('es-AR', { minimumFractionDigits: 3, maximumFractionDigits: 4 }).format(value)
export function formatDifference(value) {
  if (value === null || value === undefined) return 'No disponible'
  if (value !== 0 && Math.abs(value) < .000001) return `${value > 0 ? '+' : '−'}<0,000001`
  return new Intl.NumberFormat('es-AR', { minimumFractionDigits: 6, maximumFractionDigits: 6, signDisplay: 'exceptZero' }).format(value)
}

export function summarizeMetrics(partition) {
  const a = partition.models.find(m => m.model_id === 'A')?.metrics
  const b = partition.models.find(m => m.model_id === 'B')?.metrics
  const favored = { A: [], B: [] }, tied = [], missing = []
  for (const metric of metricDefinitions) {
    const av = a?.[metric.key], bv = b?.[metric.key]
    if (!Number.isFinite(av) || !Number.isFinite(bv)) { missing.push(metric.label); continue }
    if (av === bv) { tied.push(metric.label); continue }
    const id = (metric.key === 'brier' ? av < bv : av > bv) ? 'A' : 'B'
    favored[id].push(metric.label)
  }
  const parts = ['Síntesis de la partición seleccionada.']
  for (const id of ['A', 'B']) if (favored[id].length) parts.push(`Los valores favorecen a ${id} en ${favored[id].join(', ')}.`)
  if (favored.A.length && favored.B.length) parts.push('Hay un compromiso entre métricas: no hay un ganador general.')
  if (tied.length) parts.push(`Igualdad en ${tied.join(', ')}.`)
  if (missing.length) parts.push(`Sin comparación disponible en ${missing.join(', ')}.`)
  parts.push('Esto describe acuerdo con etiquetas experimentales, sin acreditar superioridad epidemiológica ni calibración.')
  return parts.join(' ')
}
function check(value) { if (!value) throw new Error('Contrato de análisis incompatible; consulta bloqueada.') }
function keys(value, expected) { check(value && Object.keys(value).sort().join('|') === [...expected].sort().join('|')) }

export function validateEvaluation(value, catalog) {
  keys(value, ['schema_version', 'calendar_version', 'coverage_scenario', 'coverage_verified', 'retrospective', 'previously_examined', 'operational_use_authorized', 'publication_authorized', 'evaluation_source', 'threshold', 'interpretation_limitations', 'partitions'])
  check(value.schema_version === 'sigard-retrospective-spatial-evaluation/1' && value.calendar_version === 'ar-snvs-2020-2026-v1')
  check(value.coverage_scenario === 'spatial_assumed_2024_v1' && value.coverage_verified === false && value.retrospective === true && value.previously_examined === true)
  check(value.operational_use_authorized === false && value.publication_authorized === false && value.threshold === .5 && value.evaluation_source === 'frozen_comparative_evaluation')
  check(Array.isArray(value.interpretation_limitations) && value.interpretation_limitations.length === 10)
  check(Array.isArray(value.partitions) && value.partitions.length === 3 && new Set(value.partitions.map(p => p.partition)).size === 3)
  for (const p of value.partitions) {
    keys(p, ['partition', 'target_week_start', 'target_week_end', 'week_count', 'evaluated_radio_weeks', 'models'])
    check(Object.hasOwn(partitionNames, p.partition) && Array.isArray(p.models) && p.models.length === 2 && new Set(p.models.map(m => m.model_id)).size === 2)
    let dates
    for (const m of p.models) {
      keys(m, ['model_id', 'experiment_id', 'training_version', 'metrics'])
      const source = catalog.models.find(entry => entry.model_id === m.model_id)
      check(source && source.experiment_id === m.experiment_id && source.training_version === m.training_version)
      const weeks = source.weeks.filter(w => w.evaluation_partition === p.partition).sort((a, b) => a.target_week_start.localeCompare(b.target_week_start))
      check(weeks.length === p.week_count && weeks[0]?.target_week_start === p.target_week_start && weeks.at(-1)?.target_week_end === p.target_week_end)
      const currentDates = weeks.map(w => w.target_week_start).join('|')
      check(dates === undefined || dates === currentDates); dates = currentDates
      keys(m.metrics, metricDefinitions.map(metric => metric.key))
      check(Object.values(m.metrics).every(v => v === null || (typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1)))
      check(m.metrics.brier !== null)
    }
    check(Number.isInteger(p.evaluated_radio_weeks) && p.evaluated_radio_weeks > 0 && p.evaluated_radio_weeks <= 263 * p.week_count)
  }
  return value
}

export function validateHistory(value, catalog, radio) {
  keys(value, ['schema_version', 'radio_censal', 'comparisons'])
  check(value.schema_version === 'sigard-retrospective-spatial-score/1' && value.radio_censal === radio && Array.isArray(value.comparisons))
  const weeks = [...new Set(catalog.models.flatMap(model => model.weeks.map(w => w.target_week_start)))].sort()
  check(value.comparisons.length === weeks.length)
  for (let i = 0; i < weeks.length; i++) {
    const comparison = value.comparisons[i]
    validateComparison(comparison, catalog, radio, weeks[i])
    const expected = catalog.models.filter(model => model.weeks.some(w => w.target_week_start === weeks[i]))
    check(comparison.results.length === expected.length)
  }
  return value
}

export function scoreSegments(comparisons, model) {
  const segments = []
  let current = [], previous
  for (const comparison of comparisons) {
    const row = comparison.results.find(result => result.model_id === model)?.rows[0]
    const time = Date.parse(comparison.target_week_start + 'T00:00:00Z')
    if (row?.score_status !== 'available' || (previous !== undefined && time - previous !== 7 * 86400000)) {
      if (current.length) segments.push(current)
      current = []
    }
    if (row?.score_status === 'available') current.push({ week: comparison.target_week_start, time, score: row.experimental_score })
    previous = time
  }
  if (current.length) segments.push(current)
  return segments
}
