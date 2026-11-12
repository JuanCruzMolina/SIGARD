export const schema = 'sigard-historical-backtest/1'
const contextKeys = ['dataset_version', 'campaign_version', 'data_policy_version', 'territory_version']
const statuses = ['available', 'outside_coverage', 'insufficient_training_support', 'territorial_uncertainty', 'outside_common_territory', 'privacy_suppressed']
const check = condition => { if (!condition) throw new Error('El backtesting devolvió un contrato inconsistente. Consulta bloqueada.') }
const day = text => /^\d{4}-\d{2}-\d{2}$/.test(text) && Number.isFinite(Date.parse(`${text}T00:00:00Z`))
const numeric = value => value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0)
export const statusNames = {
  available: 'Evaluable', outside_coverage: 'Fuera de cobertura', insufficient_training_support: 'Sin soporte de entrenamiento',
  territorial_uncertainty: 'Atribución territorial incierta', outside_common_territory: 'Fuera del universo común',
  privacy_suppressed: 'Protegido por privacidad',
}
export const qualityNames = { approximate: 'Aproximada', provisional: 'Provisional', verified: 'Verificada', no_assigned_record: 'Sin registros asignados', withheld: 'Detalle protegido' }
export const confusionNames = { TP: 'Verdadero positivo', FP: 'Falso positivo', FN: 'Falso negativo', TN: 'Verdadero negativo' }
export const formatValue = (value, digits = 2) => value === null || value === undefined ? 'No disponible' : new Intl.NumberFormat('es-AR', { maximumFractionDigits: digits }).format(value)

export function experimentalView(result, source = 'ml') {
  if (source === 'reference') return result
  return { ...result, rows: result.rows.map(r => ({ ...r,
    predicted: { presence_score: r.ml?.presence_score ?? null, presence: r.ml?.presence ?? null, quantity: r.ml?.quantity ?? null },
    confusion: r.ml?.confusion ?? null, presence_threshold: r.ml?.presence_threshold ?? null,
    difference: r.ml?.difference ?? null, absolute_error: r.ml?.absolute_error ?? null,
  })) }
}

function context(value, catalog) {
  check(value?.schema_version === schema && contextKeys.every(k => typeof value[k] === 'string' && value[k]))
  if (catalog) check(contextKeys.every(k => value[k] === catalog[k]))
}
export function validateBacktestCatalog(value) {
  context(value)
  check(value.calendar_version === 'ar-snvs-2020-2026-v1' && Array.isArray(value.weeks) && value.weeks.length > 0)
  check(Array.isArray(value.radio_ids) && value.radio_ids.length === 263 && new Set(value.radio_ids).size === 263)
  check(value.radio_ids.every(id => /^\d{9}$/.test(id)))
  value.weeks.forEach((w, i) => {
    check(Number.isInteger(w.target_year) && Number.isInteger(w.target_epi_week) && w.target_epi_week >= 1 && w.target_epi_week <= 53)
    check(day(w.target_week) && day(w.target_end) && day(w.origin_week) && day(w.origin_end) && statuses.includes(w.availability_status))
    check(Date.parse(w.target_week) - Date.parse(w.origin_week) === 7 * 86400000)
    check(Date.parse(w.target_end) - Date.parse(w.target_week) === 6 * 86400000)
    if (i) check(Date.parse(w.target_week) - Date.parse(value.weeks[i - 1].target_week) === 7 * 86400000)
  })
  return value
}
export function validateBacktestMetadata(value, catalog) {
  context(value, catalog)
  check(value.evaluation_type === 'event_time_retrospective_reconstruction' && value.horizon_weeks === 1)
  check(value.selected_methods?.presence === 'presence_seasonal' && value.selected_methods?.quantity === 'count_latest')
  check(value.operational_enabled === false && value.alerts_enabled === false && value.reference_is_not_trained_ml === true)
  return value
}
export function validateBacktestGeometry(value, catalog) {
  check(value?.type === 'FeatureCollection' && value.features?.length === catalog.radio_ids.length)
  const ids = value.features.map(f => f.properties?.radio_id)
  check(new Set(ids).size === ids.length && ids.every(id => catalog.radio_ids.includes(id)))
  check(value.features.every(f => ['Polygon', 'MultiPolygon'].includes(f.geometry?.type) && typeof f.properties.common_mask === 'boolean'))
  check(value.features.filter(f => f.properties.common_mask).length === 256)
  return value
}
export function validateBacktestWeek(value, catalog, selected, mode) {
  context(value, catalog)
  check(['target_week', 'target_year', 'target_epi_week', 'origin_week', 'origin_end', 'availability_status'].every(k => value[k] === selected[k]))
  check(value.rows?.length === 263 && new Set(value.rows.map(r => r.radio_id)).size === 263)
  check(value.rows.every(r => catalog.radio_ids.includes(r.radio_id) && statuses.includes(r.availability_status)))
  for (const r of value.rows) {
    if (r.ml) {
      check(['quantity', 'presence_score', 'presence', 'presence_threshold'].every(k => numeric(r.ml[k])))
      check([0, 1, null].includes(r.ml.presence) && (r.ml.presence_score === null || r.ml.presence_score <= 1))
      if (r.availability_status !== 'available') check(Object.values(r.ml).every(v => v === null))
      if (r.ml.quantity !== null) {
        check(r.ml.difference === r.ml.quantity - r.observed.quantity && r.ml.absolute_error === Math.abs(r.ml.difference))
        if (mode === 'presentation') check(r.ml.quantity >= 5)
      }
      if (r.ml.presence_score !== null) {
        check(r.ml.presence === Number(r.ml.presence_score >= r.ml.presence_threshold))
        const [p, y] = [r.ml.presence, r.observed.presence]
        check(r.ml.confusion === (p && y ? 'TP' : p ? 'FP' : y ? 'FN' : 'TN'))
      }
    }
    check(['quantity', 'presence', 'presence_score'].every(k => numeric(r.predicted[k])))
    check(numeric(r.observed.quantity) && numeric(r.observed.presence) && numeric(r.baseline.quantity))
    check([0, 1, null].includes(r.observed.presence) && [0, 1, null].includes(r.predicted.presence))
    if (r.availability_status !== 'available') check(Object.values(r.predicted).every(v => v === null) && r.baseline.quantity === null)
    else {
      check(r.common_mask && r.predicted.presence_score <= 1 && r.presence_threshold >= 0 && r.presence_threshold <= 1)
      check(r.predicted.presence === Number(r.predicted.presence_score >= r.presence_threshold))
      check(r.observed.quantity !== null && r.predicted.quantity !== null && r.baseline.quantity !== null)
      check(r.difference === r.predicted.quantity - r.observed.quantity && r.absolute_error === Math.abs(r.difference))
      const [p, y] = [r.predicted.presence, r.observed.presence]
      check(r.confusion === (p && y ? 'TP' : p ? 'FP' : y ? 'FN' : 'TN'))
    }
  }
  if (value.availability_status === 'available') check(day(value.fit_last_target_end) && Date.parse(value.origin_week) - Date.parse(value.fit_last_target_end) > 28 * 86400000)
  for (const m of Object.values(value.ml || {})) {
    check(['available', 'not_available'].includes(m.availability_status))
    if (m.availability_status === 'available') check(m.state === 'experimental_evaluated' && m.calibrated === false
      && day(m.fit_last_target_end) && Date.parse(value.origin_week) - Date.parse(m.fit_last_target_end) > 28 * 86400000)
  }
  check(value.metrics.n_comparable === value.rows.filter(r => r.availability_status === 'available').length)
  if (mode) {
    check(value.module_version === 'sigard-predictive-experimental/1' && value.disclosure?.mode === mode)
    if (mode === 'presentation') {
      check(value.department.observed_total === null)
      check(value.rows.every(r => [r.observed.quantity, r.predicted.quantity, r.baseline.quantity].every(v => v === null || v >= 5)))
    }
  }
  return value
}
export function validateBacktestHistory(value, catalog, start, end, radio, mode) {
  context(value, catalog)
  check(value.start === start && value.end === end && value.selected_radio === (radio || null))
  const expected = catalog.weeks.filter(w => w.target_week >= start && w.target_week <= end)
  check(value.series?.length === expected.length)
  value.series.forEach((w, i) => {
    check(w.target_week === expected[i].target_week && (w.availability_status === expected[i].availability_status || radio && w.availability_status === 'outside_common_territory'))
    check([w.observed, w.predicted, w.baseline].every(numeric))
    if ('ml_predicted' in w) check(numeric(w.ml_predicted))
    if (w.availability_status !== 'available') check(w.predicted === null && w.baseline === null)
  })
  if (mode) check(value.module_version === 'sigard-predictive-experimental/1' && value.disclosure?.mode === mode)
  return value
}

// SVG paths break at every unknown. They never interpolate unavailable weeks.
export function lineSegments(series, key, x, y) {
  const paths = []; let path = []
  series.forEach((w, i) => {
    if (w[key] === null) { if (path.length) paths.push(path); path = [] }
    else path.push([x(i), y(w[key])])
  })
  if (path.length) paths.push(path)
  return paths.map(points => points.map(([a, b], i) => `${i ? 'L' : 'M'}${a},${b}`).join(' '))
}
