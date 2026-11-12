import { isLocalResearchContext, validateCatalog, validateScores, validateResolvedDate, validateDateQuery } from './experimentalContract.mjs'
import { validateEvaluation, validateHistory } from './experimentalAnalysis.mjs'
import { demoMode } from './demoMode'

export function localResearchEnabled() {
  return !demoMode && isLocalResearchContext({ DEV: import.meta.env.DEV }, window.location.origin)
}

export async function researchRequest(path, signal) {
  if (!localResearchEnabled()) throw new Error('La investigación experimental sólo está disponible en desarrollo local.')
  let response
  const timeout = AbortSignal.timeout(15000)
  const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout
  try {
    response = await fetch(`http://127.0.0.1:8765/api/v1/research/spatial${path}`, {
      method: 'GET', headers: { 'X-Sigard-Research': 'local-read' },
      cache: 'no-store', credentials: 'omit', redirect: 'error', signal: requestSignal,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    if (timeout.aborted) throw new Error('La API experimental tardó demasiado. Reintentá la consulta.', { cause: error })
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
  try {
    return await response.json()
  } catch (error) {
    if (signal?.aborted) throw error
    throw new Error(timeout.aborted ? 'La API experimental tardó demasiado. Reintentá la consulta.' : 'La API experimental devolvió una respuesta incompleta. Reintentá la consulta.', { cause: error })
  }
}

export async function researchCatalog(signal) { return validateCatalog(await researchRequest('/models', signal)) }
export async function researchDate(date, signal) {
  return validateResolvedDate(await researchRequest(`/calendar?date=${encodeURIComponent(date)}`, signal), date)
}
export async function researchDateQuery(model, date, radios, temporal, signal) {
  return validateDateQuery(await researchRequest(`/query?date=${encodeURIComponent(date)}&model=${model.model_id}`, signal), date, model, radios, temporal)
}
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
