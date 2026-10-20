import { isLocalResearchContext, validateCatalog, validateScores } from './experimentalContract.mjs'
import { validateEvaluation, validateHistory } from './experimentalAnalysis.mjs'

export function localResearchEnabled() {
  return isLocalResearchContext({ DEV: import.meta.env.DEV }, window.location.origin)
}

export async function researchRequest(path, signal) {
  if (!localResearchEnabled()) throw new Error('La investigación experimental sólo está disponible en desarrollo local.')
  let response
  try {
    response = await fetch(`http://127.0.0.1:8765/api/v1/research/spatial${path}`, {
      method: 'GET', headers: { 'X-Sigard-Research': 'local-read' },
      cache: 'no-store', credentials: 'omit', redirect: 'error', signal,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new Error('No se pudo contactar con la API experimental. Comprobá que esté iniciada y reintentá.', { cause: error })
  }
  if (!response.ok) {
    const messages = {
      403: 'Acceso limitado al equipo local. Abrí SIGARD en http://127.0.0.1:5173/mapa.',
      503: 'La API no pudo verificar la integridad de los resultados experimentales. Consulta bloqueada.',
    }
    const error = new Error(messages[response.status] || 'Resultado experimental no disponible.')
    error.status = response.status
    throw error
  }
  return response.json()
}

export async function researchCatalog(signal) { return validateCatalog(await researchRequest('/models', signal)) }
export async function researchScores(model, week, radios, signal) {
  const data = await researchRequest(`/models/${model.model_id}/scores/${encodeURIComponent(week)}?experiment_id=${encodeURIComponent(model.experiment_id)}`, signal)
  return validateScores(data, model, week, radios)
}

export async function researchEvaluation(catalog, signal) {
  return validateEvaluation(await researchRequest('/evaluation', signal), catalog)
}

export async function researchHistory(catalog, radio, signal) {
  return validateHistory(await researchRequest(`/history/${encodeURIComponent(radio)}`, signal), catalog, radio)
}
