// Plain-language presentation rules for the predictive module. Pure functions only:
// they read values already delivered (and protected) by the API; no metric is computed here.

export const COMMON_RADIOS = 256

export const PROTECTED_NOTE = 'En modo protegido sólo se muestran radios con 5 o más registros; por eso no aparecen falsas alarmas y estas cifras no miden el desempeño del modelo. El desempeño general está en ¿Qué tan bien funciona el modelo?'
export const PRIVATE_WARNING = 'Modo privado: no proyectar ni compartir capturas'
export const PROTECTED_EMPTY = 'En esta semana hubo muy pocos registros por radio. Para proteger la privacidad no se muestran detalles.'

export const outcomeNames = { TP: 'Acierto', FP: 'Falsa alarma', FN: 'No anticipado', TN: 'Correctamente sin alerta' }
export const statusPlain = {
  available: 'Semana con resultado verificable', outside_coverage: 'Fuera del período con datos',
  insufficient_training_support: 'Sin predicción para esta semana', territorial_uncertainty: 'Ubicación de registros incierta',
  outside_common_territory: 'Fuera del universo común', privacy_suppressed: 'Protegido por privacidad',
}

// Method descriptions keyed by the method id delivered in metadata. A new candidate or
// reference only needs an entry here; components never name methods directly.
export const METHOD_HELP = {
  presence_seasonal: 'Método simple: estima según cómo se comportó cada radio en esta época del año en años anteriores. No usa clima.',
  count_latest: 'Método simple: repite lo observado en cada radio la semana anterior. No usa clima.',
  rf_A_epi_climate: 'Modelo de aprendizaje automático (bosque aleatorio) que combina historia reciente del radio y sus vecinos, época del año y clima de la ciudad. Prioriza los radios cuyo puntaje supera un umbral.',
  residual_h1: 'Modelo de aprendizaje automático que corrige lo observado la semana anterior con historia reciente, época del año y clima de la ciudad.',
  rf_v2_city_propensity: 'Modelo de aprendizaje automático (bosque aleatorio) que combina la actividad de toda la ciudad, la historia de cada radio y de sus vecinos, la época del año y el clima. Marca los 10 radios con mayor prioridad cada semana.',
  residual_v2: 'Modelo de aprendizaje automático que corrige lo observado la semana anterior usando la actividad de toda la ciudad, la historia de cada radio, la época del año y el clima.',
}
// Short names for the model selector; unknown ids fall back to the id itself.
export const METHOD_NAMES = {
  rf_A_epi_climate: 'Bosque aleatorio v1 (umbral)',
  residual_h1: 'Corrección de la semana anterior v1',
  rf_v2_city_propensity: 'Bosque aleatorio v2 (10 radios por semana)',
  residual_v2: 'Corrección de la semana anterior v2',
}

// Global verdict per candidate: fixed text from the documented closure of each campaign
// (docs/predictive-module-final.md, ml-candidates-closure and the corrective v2 report).
// Single place to update when a new candidate is integrated.
const NOT_OPERATIONAL = '2024 es una comparación ya observada; ningún modelo está aprobado para uso operativo.'
export const GLOBAL_VERDICTS = [{
  candidates: ['rf_A_epi_climate', 'residual_h1'],
  source: 'Cierre documentado de los candidatos (campaña sigard-predictive-motor-h1-20261102-v1)',
  text: [
    'Ninguno de los dos modelos ML superó al método de referencia con la estabilidad exigida por los criterios fijados antes de evaluarlos (años de desarrollo 2021–2023).',
    'Por eso el método de referencia sigue siendo el seleccionado y los modelos ML se muestran sólo como experimentos evaluados, sin aprobación para uso operativo.',
    'En ¿Dónde?, agregar clima mejoró el ajuste de las probabilidades frente al mismo modelo sin clima, pero no frente al método de referencia. En ¿Cuántos?, el aporte del clima no está demostrado.',
    '2024 ya se había observado durante el desarrollo: es una comparación, no una validación externa.',
  ],
}, {
  candidates: ['rf_v2_city_propensity'],
  source: 'Campaña correctiva v2 prerregistrada (sigard-two-capabilities-h1-corrective-20261112-v1): no promovido',
  text: [
    'Resultado similar al método de repetir la semana anterior (recall@10 0,160 frente a 0,156; diferencia no significativa). Mejor que los modelos anteriores.',
    NOT_OPERATIONAL,
  ],
}, {
  candidates: ['residual_v2'],
  source: 'Campaña correctiva v2 prerregistrada (sigard-two-capabilities-h1-corrective-20261112-v1): no promovido',
  text: [
    // 13,6 %: (0,035357 − 0,030535) / 0,035357 with the unrounded frozen MAE values.
    'Error promedio 13,6 % menor que repetir la semana anterior en 2021–2023 (diferencia con intervalo de confianza que excluye 0). Subestima semanas de muchos casos.',
    NOT_OPERATIONAL,
  ],
}]
export function candidatesFor(metadata, view) {
  return (metadata?.experimental_candidates || []).filter(c => c.capability === view)
}
// Requested model if it belongs to the question; otherwise the default from metadata.
export function selectedCandidate(metadata, view, requested) {
  const ids = candidatesFor(metadata, view).map(c => c.id)
  if (ids.includes(requested)) return requested
  const fallback = metadata?.default_candidates?.[view]
  return ids.includes(fallback) ? fallback : ids[0] || null
}
export function globalVerdict(metadata, candidate) {
  if (!candidate || !(metadata?.experimental_candidates || []).some(c => c.id === candidate)) return null
  return GLOBAL_VERDICTS.find(v => v.candidates.includes(candidate)) || null
}
export const candidateName = id => METHOD_NAMES[id] || id
export function decisionText(candidate) {
  const rule = candidate?.decision_rule
  if (rule?.type === 'top_k') return `Marca los ${rule.k} radios con mayor prioridad cada semana.`
  if (rule?.type === 'threshold') return 'Prioriza los radios cuyo puntaje supera un umbral fijado en el entrenamiento.'
  return 'Estima la cantidad de registros de cada radio.'
}

export function methodSources(metadata, view, requested) {
  const sources = []
  const id = selectedCandidate(metadata, view, requested)
  const candidate = candidatesFor(metadata, view).find(c => c.id === id)
  if (candidate) sources.push({ source: 'ml', label: 'Modelo ML', short: 'el modelo ML', method: id, name: candidateName(id),
    help: METHOD_HELP[id] || '', candidate })
  const reference = metadata?.selected_methods?.[view]
  sources.push({ source: 'reference', label: 'Método de referencia', short: 'el método de referencia', method: reference,
    name: metadata?.method_labels?.[view] || reference, help: METHOD_HELP[reference] || '' })
  return sources
}

const number = (value, digits = 0) => value === null || value === undefined ? '—' : new Intl.NumberFormat('es-AR', { maximumFractionDigits: digits }).format(value)
export const formatPlain = number
const day = (text, opts) => new Intl.DateTimeFormat('es-AR', { timeZone: 'UTC', ...opts }).format(new Date(`${text}T00:00:00Z`))
export function weekLabel(w) {
  if (!w) return ''
  return `${day(w.target_week, { day: 'numeric', month: 'short' })} al ${day(w.target_end, { day: 'numeric', month: 'short', year: 'numeric' })}`
}
export const dateLabel = text => text ? day(text, { day: 'numeric', month: 'short', year: 'numeric' }) : ''

export function yearOptions(weeks) {
  const years = [...new Set(weeks.map(w => w.target_year))]
  return years.map(year => {
    const list = weeks.filter(w => w.target_year === year)
    const available = list.some(w => w.availability_status === 'available')
    const status = available ? null : list[0].availability_status
    return { year, available, label: available ? String(year) : `${year} · ${status === 'outside_coverage' ? 'sin datos' : 'sin predicción'}` }
  })
}
export const latestEvaluableYear = weeks => Math.max(...weeks.filter(w => w.availability_status === 'available').map(w => w.target_year))

// Most disclosable radios in the active mode; ties: more records, then the latest week.
export function mostActiveWeek(series) {
  const candidates = (series || []).filter(w => w.availability_status === 'available' && w.n_comparable > 0)
  if (!candidates.length) return null
  return candidates.reduce((best, w) => {
    const a = [w.n_comparable, w.observed ?? -1, w.target_week], b = [best.n_comparable, best.observed ?? -1, best.target_week]
    return a[0] > b[0] || (a[0] === b[0] && (a[1] > b[1] || (a[1] === b[1] && a[2] > b[2]))) ? w : best
  }).target_week
}

const VIEWS = { donde: 'presence', cuantos: 'quantity' }
const MODEL = /^[A-Za-z0-9_]{1,60}$/
const METHODS = { ml: 'ml', referencia: 'reference', comparar: 'compare' }
const invert = o => Object.fromEntries(Object.entries(o).map(([k, v]) => [v, k]))
// Disclosure mode is never read from or written to the URL: a shared link always opens protected.
export function readUrlState(params) {
  const year = Number(params.get('anio')), week = Number(params.get('se')), radio = params.get('radio')
  return {
    year: Number.isInteger(year) && year >= 2000 ? year : null, week: Number.isInteger(week) && week >= 1 && week <= 53 ? week : null,
    view: VIEWS[params.get('vista')] || 'presence', method: METHODS[params.get('metodo')] || 'ml',
    layer: params.get('capa') === 'observados' ? 'observed' : 'expected', radio: /^\d{9}$/.test(radio || '') ? radio : '',
    model: MODEL.test(params.get('modelo') || '') ? params.get('modelo') : '',
  }
}
export function writeUrlState(state) {
  const params = new URLSearchParams()
  if (state.year && state.week) { params.set('anio', String(state.year)); params.set('se', String(state.week)) }
  params.set('vista', invert(VIEWS)[state.view] || 'donde'); params.set('metodo', invert(METHODS)[state.method] || 'ml')
  if (state.model) params.set('modelo', state.model)
  if (state.layer === 'observed') params.set('capa', 'observados')
  if (state.radio) params.set('radio', state.radio)
  return params
}

export function cellCategory(row, view) {
  if (!row) return 'nodata'
  if (row.availability_status === 'privacy_suppressed') return 'protected'
  if (row.availability_status === 'outside_common_territory' || !row.common_mask) return 'outside'
  if (row.availability_status !== 'available') return 'nodata'
  if (view === 'presence') return row.confusion || 'nodata'
  return row.predicted.quantity === null ? 'nodata' : 'value'
}

export const QUANTITY_BINS = [
  { upper: 0, label: '0 registros', color: '#f7f8f4' }, { upper: 1, label: 'Hasta 1', color: '#c2dfd4' },
  { upper: 2, label: '1 a 2', color: '#88bca9' }, { upper: 5, label: '2 a 5', color: '#459781' },
  { upper: 10, label: '5 a 10', color: '#176d60' }, { upper: Infinity, label: 'Más de 10', color: '#0b3336' },
]
export const binFor = value => QUANTITY_BINS.find(b => value <= b.upper)

const STATUS_ITEMS = [
  { key: 'protected', label: 'Protegido por privacidad (no significa cero)' },
  { key: 'outside', label: 'Fuera del universo común' },
  { key: 'nodata', label: 'Sin dato' },
]
// Protected mode only shows cells with 5 or more records: categories or ranges that can
// never appear there are not offered.
export function legendItems(view, mode) {
  if (view === 'presence') {
    const outcomes = [
      { key: 'TP', label: 'Priorizado y con registros (acierto)' },
      ...(mode === 'private' ? [{ key: 'FP', label: 'Priorizado sin registros (falsa alarma)' }] : []),
      { key: 'FN', label: 'Con registros no priorizado (no anticipado)' },
      ...(mode === 'private' ? [{ key: 'TN', label: 'Sin registros ni prioridad (correctamente sin alerta)' }] : []),
    ]
    return [...outcomes, ...STATUS_ITEMS]
  }
  const bins = QUANTITY_BINS.filter(b => mode === 'private' || b.upper > 5).map(b => ({ key: `bin-${b.upper}`, label: b.label, color: b.color }))
  return [...bins, ...STATUS_ITEMS]
}

// Sources carry the candidate id in `method`; ML metrics are keyed by candidate.
export const sourceMetrics = (result, source) => source.source === 'ml' ? result.ml_metrics?.[source.method] : result.metrics
export const sourceAvailable = (result, source) => source.source !== 'ml' || result.ml?.[source.method]?.availability_status === 'available'

export function unavailableMessage(result) {
  const status = result.availability_status
  if (status === 'insufficient_training_support') return { title: 'Sin predicción para esta semana', text: 'En 2020 todavía no había suficientes semanas previas para que los métodos aprendieran. Esta semana sólo se usa como historia.' }
  if (status === 'outside_coverage') return { title: 'Fuera del período con datos', text: 'Esta semana está fuera del período cubierto por el proyecto (2020–2024). No hay registros ni predicciones.' }
  return { title: 'Comparación no disponible', text: 'La ubicación de los registros de esta semana no permite comparar por radio.' }
}

// Summary cards for one week. In protected mode the visible subset contains only radios
// with 5 or more records, so performance wording (precision, false alarms) is excluded.
export function summaryCards({ result, view, primary, other, mode }) {
  if (result.availability_status !== 'available') return { kind: 'unavailable', ...unavailableMessage(result) }
  if (!result.metrics.n_comparable) return { kind: 'protected', title: 'Sin detalles divulgables', text: mode === 'presentation' ? PROTECTED_EMPTY : 'No hay radios comparables para esta semana.' }
  const visible = result.metrics.n_comparable
  const get = s => sourceAvailable(result, s) ? sourceMetrics(result, s) : null
  const p = get(primary), o = other ? get(other) : null
  const missing = s => `${s.label}: sin predicción guardada para esta semana`
  const cards = []
  if (mode === 'presentation') {
    cards.push({ id: 'visible', label: 'Radios visibles', value: `${number(visible)} de ${COMMON_RADIOS}`, detail: 'Con 5 o más registros; los demás radios se ocultan.' })
    if (view === 'presence') {
      const flagged = m => m ? m.presence.confusion.TP + m.presence.confusion.FP : null
      cards.push({ id: 'primary', label: `Priorizados por ${primary.label}`, value: p ? number(flagged(p)) : '—', detail: p ? 'entre los radios visibles' : missing(primary) })
      cards.push({ id: 'records', label: 'Registros en los radios visibles', value: number(result.metrics.totals.observed), detail: p && p.totals.predicted !== null ? `${primary.label} esperaba ${number(p.totals.predicted)} en los radios visibles` : 'entre los radios visibles' })
      if (other) cards.push({ id: 'other', label: `Frente a ${other.label}`, value: o ? `${number(flagged(o))} priorizados` : '—', detail: o ? 'entre los mismos radios visibles' : missing(other), help: other.help })
    } else {
      cards.push({ id: 'primary', label: `Registros esperados por ${primary.label}`, value: p ? number(p.totals.predicted) : '—', detail: p ? 'en los radios visibles' : missing(primary) })
      cards.push({ id: 'records', label: 'Registros observados', value: number(result.metrics.totals.observed), detail: 'en los radios visibles' })
      if (other) cards.push({ id: 'other', label: `Frente a ${other.label}`, value: o ? `${number(o.totals.predicted)} esperados` : '—', detail: o ? 'en los mismos radios visibles' : missing(other), help: other.help })
    }
    return { kind: 'cards', cards, note: PROTECTED_NOTE }
  }
  if (view === 'presence') {
    const c = m => m.presence.confusion
    cards.push({ id: 'primary', label: `Radios priorizados por ${primary.label}`, value: p ? number(c(p).TP + c(p).FP) : '—', detail: p ? `Radios priorizados que tuvieron registros: ${number(c(p).TP)} · falsas alarmas: ${number(c(p).FP)}` : missing(primary) })
    cards.push({ id: 'anticipated', label: `Radios con registros que ${primary.short} anticipó`, value: p ? `${number(c(p).TP)} de ${number(c(p).TP + c(p).FN)}` : '—', detail: p ? `No anticipados: ${number(c(p).FN)}` : missing(primary) })
    if (p?.totals.predicted === null) cards.push({ id: 'records', label: 'Registros observados en la ciudad', value: number(result.metrics.totals.observed), detail: `${primary.label} sólo prioriza radios; no estima cantidades · ${number(visible)} radios comparables` })
    else cards.push({ id: 'records', label: 'Registros esperados en la ciudad', value: p ? number(p.totals.predicted, 1) : '—', detail: `Observados: ${number(result.metrics.totals.observed)} en ${number(visible)} radios comparables` })
    if (other) cards.push({ id: 'other', label: `Frente a ${other.label}`, value: o ? `${number(c(o).TP)} de ${number(c(o).TP + c(o).FN)} anticipados` : '—', detail: o ? `${number(c(o).TP + c(o).FP)} priorizados · ${number(c(o).FP)} falsas alarmas` : missing(other), help: other.help })
  } else {
    cards.push({ id: 'primary', label: 'Registros esperados en la ciudad', value: p ? number(p.totals.predicted, 1) : '—', detail: p ? `${primary.label} · observados: ${number(result.metrics.totals.observed)}` : missing(primary) })
    cards.push({ id: 'error', label: 'Diferencia promedio por radio', value: p ? number(p.quantity.mae, 2) : '—', detail: 'registros entre lo esperado y lo observado' })
    cards.push({ id: 'positive', label: 'Radios con registros', value: number(result.metrics.quantity_positive?.n), detail: `de ${number(visible)} radios comparables` })
    if (other) cards.push({ id: 'other', label: `Frente a ${other.label}`, value: o ? `${number(o.totals.predicted, 1)} esperados` : '—', detail: o ? `Diferencia promedio por radio: ${number(o.quantity.mae, 2)}` : missing(other), help: other.help })
  }
  return { kind: 'cards', cards, note: 'Modo privado: valores exactos de todos los radios comparables.' }
}

// Descriptive input families of a model, from the feature names it declares. No values.
const FEATURE_GROUPS = [
  [/^neighbor_/, 'Actividad reciente de los radios vecinos'],
  [/temperature|humidity|precipitation/, 'Clima de la ciudad (un único punto de referencia)'],
  [/semana_epidemiologica|seno|coseno|_sin$|_cos$/, 'Época del año'],
  [/count|presence|mean_|trend|known/, 'Historia reciente de registros del radio'],
]
export function featureGroups(features) {
  const groups = []
  for (const name of features || []) {
    const label = FEATURE_GROUPS.find(([pattern]) => pattern.test(name))?.[1] || 'Características fijas del radio (superficie, vecinos)'
    if (!groups.includes(label)) groups.push(label)
  }
  return groups
}
