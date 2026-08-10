const DATA_ROOT = '/data'

async function loadJson(file) {
  const response = await fetch(`${DATA_ROOT}/${file}`)
  if (!response.ok) throw new Error(`No se pudo cargar ${file}`)
  return response.json()
}

export async function loadSigardData() {
  const [summary, backtest, geojson] = await Promise.all([
    loadJson('mvp_prediction_summary.json'),
    loadJson('mvp_backtest.json'),
    loadJson('mvp_prediction.geojson'),
  ])
  return { summary, backtest, geojson }
}

export function riskLabel(level) {
  return ({ very_low: 'Muy bajo', low: 'Bajo', medium: 'Medio', high: 'Alto' })[level] || level || 'Sin clasificar'
}

export function formatNumber(value, digits = 1) {
  return new Intl.NumberFormat('es-AR', { maximumFractionDigits: digits }).format(value ?? 0)
}

export function formatDate(value) {
  return new Intl.DateTimeFormat('es-AR', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`))
}

export function getRadioProperties(feature) {
  return feature?.properties || {}
}

export function getRadioValue(props, keys, fallback = 0) {
  for (const key of keys) if (props?.[key] !== undefined && props[key] !== null) return props[key]
  return fallback
}

export function getRisk(props) {
  return props?.risk_level || props?.risk || 'very_low'
}

export function getPredictedCases(props) {
  return Number(getRadioValue(props, ['predicted_cases', 'prediction', 'predicted'], 0))
}

export function getRadioId(props) {
  return props?.radio_id || props?.id || props?.radio || '—'
}

export function getCoordinates(feature) {
  const coords = feature?.geometry?.coordinates || []
  return Array.isArray(coords[0]) ? coords[0][0] : coords
}

export const riskColors = {
  very_low: '#b8d7c4',
  low: '#4fb28a',
  medium: '#e0ae3e',
  high: '#d95c50',
}

