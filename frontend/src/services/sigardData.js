const DATA_ROOT = '/data'
const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
export const DATA_ERROR_MESSAGE = 'No fue posible cargar los datos del prototipo.'

async function loadStaticJson(file) {
  const response = await fetch(`${DATA_ROOT}/${file}`)
  if (!response.ok) throw new Error(DATA_ERROR_MESSAGE)
  return response.json()
}

async function loadApiJson(path) {
  const response = await fetch(`${API_URL}/api/v1/public${path}`)
  if (!response.ok) throw new Error(`API pública no disponible: ${response.status}`)
  return response.json()
}

async function loadFromApi() {
  const availableWeeks = await loadApiJson('/weeks')
  if (!Array.isArray(availableWeeks.weeks) || availableWeeks.weeks.length === 0) throw new Error(DATA_ERROR_MESSAGE)
  const [territorialContext, modelEvaluation, metadata, predictions, experimentalCollections] = await Promise.all([
    loadApiJson('/territorial-context'),
    loadApiJson('/model-evaluation'),
    loadApiJson('/metadata'),
    Promise.all(availableWeeks.weeks.map((week) => loadApiJson(`/predictions/${encodeURIComponent(week.cutoff_date)}`))),
    Promise.all(availableWeeks.weeks.map((week) => loadApiJson(`/experimental-spatial-history/${encodeURIComponent(week.cutoff_date)}`))),
  ])
  return {
    availableWeeks,
    temporalPredictions: { model: metadata.temporal_model, predictions },
    territorialContext,
    experimentalHistory: {
      type: 'FeatureCollection',
      features: experimentalCollections.flatMap((collection) => collection.features),
      publication: availableWeeks.publication,
    },
    modelEvaluation,
    metadata,
    dataSource: 'api',
  }
}

async function loadFromStaticFallback() {
  const [availableWeeks, temporalPredictions, territorialContext, experimentalHistory, modelEvaluation, metadata] = await Promise.all([
    loadStaticJson('available_weeks.json'), loadStaticJson('temporal_predictions.json'),
    loadStaticJson('territorial_context.geojson'), loadStaticJson('experimental_spatial_history.geojson'),
    loadStaticJson('model_evaluation.json'), loadStaticJson('mvp_metadata.json'),
  ])
  return {
    availableWeeks, temporalPredictions, territorialContext, experimentalHistory, modelEvaluation, metadata,
    dataSource: 'static-fallback',
  }
}

function assertFeatureCollection(value, label) {
  if (value?.type !== 'FeatureCollection' || !Array.isArray(value.features)) throw new Error(`${DATA_ERROR_MESSAGE} ${label} no es una colección geográfica válida.`)
}

function assertCompleteData(availableWeeks, temporalPredictions, territorialContext, experimentalHistory, modelEvaluation) {
  const expectedLevels = new Set(['very_low', 'low', 'medium', 'high'])
  const hasValidLevels = (features) => {
    const levels = new Set(features.map((feature) => feature.properties?.relative_level))
    return levels.size > 0 && [...levels].every((level) => expectedLevels.has(level))
  }
  if (territorialContext.features.length !== 263 || !hasValidLevels(territorialContext.features)) throw new Error(DATA_ERROR_MESSAGE)
  if (!Array.isArray(temporalPredictions.predictions) || !Array.isArray(modelEvaluation.backtest) || modelEvaluation.backtest.length !== 6) throw new Error(DATA_ERROR_MESSAGE)
  for (const week of availableWeeks.weeks) {
    const predictions = temporalPredictions.predictions.filter((item) => item.cutoff_date === week.cutoff_date)
    const simulation = experimentalHistory.features.filter((feature) => feature.properties?.cutoff_date === week.cutoff_date)
    const predictionMatchesTarget = predictions.length === 1 && predictions[0].target_week_start === week.target_week_start && predictions[0].target_week_end === week.target_week_end
    const simulationMatchesTarget = simulation.length === 263 && simulation.every((feature) => feature.properties?.target_week_start === week.target_week_start && feature.properties?.target_week_end === week.target_week_end)
    if (!predictionMatchesTarget || !simulationMatchesTarget || !hasValidLevels(simulation)) throw new Error(DATA_ERROR_MESSAGE)
  }
}

export async function loadSigardData() {
  try {
    let loaded
    try {
      loaded = await loadFromApi()
    } catch {
      loaded = await loadFromStaticFallback()
    }
    const { availableWeeks, temporalPredictions, territorialContext, experimentalHistory, modelEvaluation } = loaded
    if (!Array.isArray(availableWeeks.weeks) || availableWeeks.weeks.length === 0) throw new Error(`${DATA_ERROR_MESSAGE} No hay semanas disponibles.`)
    if (!availableWeeks.weeks.some((week) => week.cutoff_date === availableWeeks.default_cutoff_date)) throw new Error(`${DATA_ERROR_MESSAGE} El corte predeterminado no está disponible.`)
    assertFeatureCollection(territorialContext, 'El contexto territorial')
    assertFeatureCollection(experimentalHistory, 'La simulación espacial')
    assertCompleteData(availableWeeks, temporalPredictions, territorialContext, experimentalHistory, modelEvaluation)
    return loaded
  } catch (error) {
    if (error.message?.startsWith(DATA_ERROR_MESSAGE)) throw error
    throw new Error(DATA_ERROR_MESSAGE, { cause: error })
  }
}

export function getSelectedWeek(data, cutoffDate) {
  return data.availableWeeks.weeks.find((week) => week.cutoff_date === cutoffDate)
}

export function getSelectedPrediction(data, cutoffDate) {
  const matches = data.temporalPredictions.predictions.filter((item) => item.cutoff_date === cutoffDate)
  if (matches.length !== 1) throw new Error(`${DATA_ERROR_MESSAGE} Se esperaba una única predicción para el corte seleccionado.`)
  return matches[0]
}

export function getExperimentalCollection(data, cutoffDate) {
  const features = data.experimentalHistory.features.filter((feature) => feature.properties?.cutoff_date === cutoffDate)
  if (features.length !== 263) throw new Error(`${DATA_ERROR_MESSAGE} La simulación seleccionada no contiene exactamente 263 radios.`)
  return { type: 'FeatureCollection', features }
}

export function levelLabel(level) {
  return ({ very_low: 'Muy bajo', low: 'Bajo', medium: 'Medio', high: 'Alto' })[level] || level || 'Sin clasificar'
}

export function formatNumber(value, digits = 1) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return '—'
  return new Intl.NumberFormat('es-AR', { maximumFractionDigits: digits }).format(value)
}

export function formatDate(value) {
  if (!value) return '—'
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return value
  return new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(year, month - 1, day))
}

export function formatDateRange(start, end) { return `${formatDate(start)} – ${formatDate(end)}` }
export function getDisclaimer(metadata, kind) { return metadata?.disclaimers?.[kind] || '' }

export const levelColors = { very_low: '#b8d7c4', low: '#4fb28a', medium: '#e0ae3e', high: '#d95c50' }
