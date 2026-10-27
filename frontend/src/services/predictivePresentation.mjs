// Shared presentation of counts, never a risk scale or a presence probability.
export const countBins = [
  { limit: 1, color: '#e1eeed', label: '0–1' },
  { limit: 3, color: '#9ccbc7', label: '>1–3' },
  { limit: 10, color: '#398f88', label: '>3–10' },
  { limit: Infinity, color: '#125951', label: '>10' },
]
export function countColor(value) {
  return Number.isFinite(value) && value >= 0 ? countBins.find(bin => value <= bin.limit).color : '#9aabad'
}
export function countTooltip(props) {
  const node = document.createElement('span')
  node.textContent = `Radio ${props.radio_id} · ${Number.isFinite(props.expected_count) ? `${props.expected_count.toFixed(2)} registros estimados` : 'Datos insuficientes'}${props.estimate_status === 'available_with_historical_mean_fallback' ? ' · Sin conteo reciente: respaldo de media histórica' : ''}`
  return node
}
export function joinCountGeometry(geometry, result) {
  const rows = new Map((result?.radios || []).map(row => [row.radio_id, row]))
  return { type: 'FeatureCollection', features: geometry.features.map(feature => ({
    ...feature, properties: { radio_id: feature.properties.radio_id,
      expected_count: null, estimate_status: 'insufficient_data', ...rows.get(feature.properties.radio_id) },
  })) }
}
