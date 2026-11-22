import { localResearchEnabled } from './experimentalResults'
import { fetchRead } from './readRetry.mjs'
import { endSession, readSession, ROLE_REQUIRED, SESSION_EXPIRED, SESSION_REQUIRED, sessionError, sessionExpired } from './adminSession.mjs'
import { validateBacktestCatalog, validateBacktestGeometry, validateBacktestMetadata, validateBacktestWeek, validateBacktestHistory } from './backtestContract.mjs'

// F2: the predictive viewer API lives on the local administrative API (127.0.0.1:8767) and
// requires the administrator session of /admin/reportes (same JWT, read-only here: this
// module never stores anything in the browser). No session or an expired one → no request.
export const PREDICTIVE_API = 'http://127.0.0.1:8767/api/v1/research/predictive'

async function request(path, signal) {
  if (!localResearchEnabled()) throw new Error('El backtesting sólo está disponible en desarrollo local autorizado.')
  const token = readSession()
  if (!token) throw sessionError(SESSION_REQUIRED)
  if (sessionExpired(token)) { endSession(); throw sessionError(SESSION_EXPIRED) }
  const timeout = AbortSignal.timeout(20000)
  let response
  try {
    // One retry on a network failure or 5xx; the error below only appears if it fails too.
    response = await fetchRead(`${PREDICTIVE_API}${path}`, {
      method: 'GET', headers: { 'X-Sigard-Research': 'local-read', Authorization: `Bearer ${token}` }, cache: 'no-store', credentials: 'omit',
      redirect: 'error', signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new Error(timeout.aborted ? 'La consulta tardó demasiado. Reintentá.' : 'No se pudo conectar con la API local. Comprobá el servicio y reintentá.', { cause: error })
  }
  if (response.status === 401) { endSession(); throw sessionError(SESSION_EXPIRED) }
  if (!response.ok) {
    const detail = response.status === 403 ? await response.json().then(body => body?.detail, () => null) : null
    throw new Error(response.status === 503 ? 'El paquete de backtesting falta o no pudo verificarse. Revisá la compilación offline y reintentá.' : detail === 'Rol administrador requerido' ? ROLE_REQUIRED : response.status === 403 ? 'Abrí SIGARD en http://127.0.0.1:5173/mapa para consultar los resultados locales.' : 'El período o territorio solicitado no está disponible.')
  }
  return response.json()
}

// In-memory cache for this page session only (no browser storage). Keys include the
// disclosure mode, so protected and private responses never mix. The server still
// verifies hashes on every request it receives; a reload or retry clears this cache, and
// so does any change of administrator session (results never outlive the session).
const cache = new Map()
let cacheSession = null
function cached(path) {
  const session = readSession()
  if (session !== cacheSession) { cache.clear(); cacheSession = session }
  if (!cache.has(path)) {
    const pending = request(path).catch(error => { cache.delete(path); throw error })
    cache.set(path, pending)
  }
  return cache.get(path)
}
function abortable(promise, signal) {
  if (!signal) return promise
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason)
    signal.addEventListener('abort', () => reject(signal.reason), { once: true })
    promise.then(resolve, reject)
  })
}
export function clearBacktestCache() { cache.clear() }

const weekPath = (year, week, mode) => `/comparison?year=${year}&week=${week}&disclosure=${mode}`
// Starts a week request before the calendar is known (URL-selected week); validated later.
export function prefetchWeek(year, week, mode = 'presentation') { cached(weekPath(year, week, mode)).catch(() => {}) }

export async function backtestSetup(signal) {
  const [calendar, geo, meta] = await abortable(Promise.all([cached('/calendar'), cached('/geometry'), cached('/metadata')]), signal)
  const catalog = validateBacktestCatalog(calendar)
  return { catalog, geometry: validateBacktestGeometry(geo, catalog), metadata: validateBacktestMetadata(meta, catalog) }
}
export async function backtestWeek(catalog, week, signal, mode = 'presentation') {
  return validateBacktestWeek(await abortable(cached(weekPath(week.target_year, week.target_epi_week, mode)), signal), catalog, week, mode)
}
export async function backtestHistory(catalog, start, end, radio, signal, mode = 'presentation') {
  const query = new URLSearchParams({ start, end, disclosure: mode }); if (radio) query.set('radio', radio)
  return validateBacktestHistory(await abortable(cached(`/history?${query}`), signal), catalog, start, end, radio, mode)
}
