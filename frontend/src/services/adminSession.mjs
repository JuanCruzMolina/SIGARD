// Administrator session as seen by the predictive viewer (F2/F3). The token is the one the
// Administración login keeps in sessionStorage; this module only reads it or removes it when the
// server (or its own expiry) says it is no longer valid. It never writes any other value.
export const SESSION_KEY = 'sigard_admin_token'
export const PREDICTIVE_ROUTE = '/admin/predictivo'
export const SESSION_REQUIRED = 'Iniciá sesión con una cuenta de Administración para consultar el visor predictivo.'
export const SESSION_EXPIRED = 'La sesión de Administración venció o fue cerrada. Ingresá nuevamente para volver al visor predictivo.'
export const ROLE_REQUIRED = 'Tu cuenta no tiene rol de administrador; el visor predictivo exige una cuenta de Administración.'
// Viewer state kept in the URL (predictiveView.mjs): an old /mapa link carrying any of them was a viewer link.
export const VIEWER_PARAMS = ['anio', 'se', 'vista', 'metodo', 'capa', 'radio', 'modelo']

export function readSession(storage = globalThis.sessionStorage) {
  try { return storage.getItem(SESSION_KEY) || '' } catch { return '' }
}
export function endSession(storage = globalThis.sessionStorage) {
  try { storage.removeItem(SESSION_KEY) } catch { /* Storage unavailable: nothing to clear. */ }
}
// Reads the claims of the token without verifying it: the server always validates it.
function claims(token) {
  try { return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))) } catch { return null }
}
export function sessionExpired(token, now = Date.now()) {
  const exp = claims(token)?.exp
  return typeof exp !== 'number' || exp * 1000 <= now
}
// Milliseconds until the token expires (0 when already expired or unreadable).
export function sessionRemaining(token, now = Date.now()) {
  const exp = claims(token)?.exp
  return typeof exp === 'number' ? Math.max(0, exp * 1000 - now) : 0
}
// Interface gate only (the API enforces the role): unexpired token declaring the admin role.
export function adminSessionActive(token, now = Date.now()) {
  return Boolean(token) && !sessionExpired(token, now) && claims(token)?.role === 'admin'
}
export const hasViewerParams = params => VIEWER_PARAMS.some(name => params.has(name))
export function sessionError(message) { const error = new Error(message); error.session = true; return error }
