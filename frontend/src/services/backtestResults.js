import { localResearchEnabled } from './experimentalResults'
import { validateBacktestCatalog, validateBacktestGeometry, validateBacktestMetadata, validateBacktestWeek, validateBacktestHistory } from './backtestContract.mjs'

async function request(path, signal) {
  if (!localResearchEnabled()) throw new Error('El backtesting sólo está disponible en desarrollo local autorizado.')
  const timeout = AbortSignal.timeout(20000)
  let response
  try {
    response = await fetch(`http://127.0.0.1:8765/api/v1/research/predictive${path}`, {
      method: 'GET', headers: { 'X-Sigard-Research': 'local-read' }, cache: 'no-store', credentials: 'omit',
      redirect: 'error', signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new Error(timeout.aborted ? 'La consulta tardó demasiado. Reintentá.' : 'No se pudo conectar con la API local. Comprobá el servicio y reintentá.', { cause: error })
  }
  if (!response.ok) throw new Error(response.status === 503 ? 'El paquete de backtesting falta o no pudo verificarse. Revisá la compilación offline y reintentá.' : response.status === 403 ? 'Abrí SIGARD en http://127.0.0.1:5173/mapa para consultar los resultados locales.' : 'El período o territorio solicitado no está disponible.')
  return response.json()
}
export async function backtestSetup(signal) {
  const catalog = validateBacktestCatalog(await request('/calendar', signal))
  const [geo, meta] = await Promise.all([request('/geometry', signal), request('/metadata', signal)])
  return { catalog, geometry: validateBacktestGeometry(geo, catalog), metadata: validateBacktestMetadata(meta, catalog) }
}
export async function backtestWeek(catalog, week, signal, mode = 'presentation') {
  return validateBacktestWeek(await request(`/comparison?year=${week.target_year}&week=${week.target_epi_week}&disclosure=${mode}`, signal), catalog, week, mode)
}
export async function backtestHistory(catalog, start, end, radio, signal, mode = 'presentation') {
  const query = new URLSearchParams({ start, end, disclosure: mode }); if (radio) query.set('radio', radio)
  return validateBacktestHistory(await request(`/history?${query}`, signal), catalog, start, end, radio, mode)
}
