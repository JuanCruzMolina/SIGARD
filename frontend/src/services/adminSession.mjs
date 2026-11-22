// Administrator session as seen by the predictive viewer service (F2). The token is the one
// /admin/reportes keeps in sessionStorage; this module only reads it or removes it when the
// server (or its own expiry) says it is no longer valid. It never writes any other value.
export const SESSION_KEY = 'sigard_admin_token'
export const SESSION_REQUIRED = 'Iniciá sesión en Administración (http://127.0.0.1:5173/admin/reportes) para consultar el visor predictivo y volvé a esta página.'
export const SESSION_EXPIRED = 'La sesión de Administración venció o fue cerrada. Volvé a ingresar en http://127.0.0.1:5173/admin/reportes y reintentá.'
export const ROLE_REQUIRED = 'Tu cuenta no tiene rol de administrador; el visor predictivo exige una cuenta de Administración.'

export function readSession(storage = globalThis.sessionStorage) {
  try { return storage.getItem(SESSION_KEY) || '' } catch { return '' }
}
export function endSession(storage = globalThis.sessionStorage) {
  try { storage.removeItem(SESSION_KEY) } catch { /* Storage unavailable: nothing to clear. */ }
}
// Reads only the expiry of the token (no verification: the server always validates it).
export function sessionExpired(token, now = Date.now()) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return typeof payload.exp !== 'number' || payload.exp * 1000 <= now
  } catch { return true }
}
export function sessionError(message) { const error = new Error(message); error.session = true; return error }

