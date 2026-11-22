import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AdminLoginForm from '../components/AdminLoginForm'
import HistoricalBacktest from '../components/HistoricalBacktest'
import { PageIntro } from '../components/SigardComponents'
import { clearBacktestCache } from '../services/backtestResults'
import { adminSessionActive, endSession, readSession, ROLE_REQUIRED, SESSION_EXPIRED, SESSION_REQUIRED, sessionExpired, sessionRemaining } from '../services/adminSession.mjs'
import { localResearchEnabled } from '../services/experimentalResults'
import '../Prevention.css'

// F3: the predictive viewer inside Administración. Only an unexpired administrator session
// renders it; otherwise the login is shown here and, once logged in, the same URL (with its
// anio/se/vista/metodo/capa/radio/modelo state) opens the viewer. The API still checks every request.
export default function AdminPredictivo() {
  const [token, setToken] = useState(readSession)
  const [notice, setNotice] = useState(() => {
    const stored = readSession()
    return stored && sessionExpired(stored) ? SESSION_EXPIRED : stored && !adminSessionActive(stored) ? ROLE_REQUIRED : SESSION_REQUIRED
  })
  const leave = useCallback(message => { endSession(); clearBacktestCache(); setToken(''); setNotice(message) }, [])
  const active = localResearchEnabled() && adminSessionActive(token)

  // Expiry (60 min) while the viewer is open: back to the login before any request fails.
  useEffect(() => {
    if (!active) return undefined
    const timer = setTimeout(() => leave(SESSION_EXPIRED), Math.min(sessionRemaining(token), 2 ** 31 - 1))
    return () => clearTimeout(timer)
  }, [active, token, leave])
  // An expired token found on arrival is cleared so it is never sent.
  useEffect(() => { if (token && sessionExpired(token)) endSession() }, [token])

  if (!localResearchEnabled()) return <main className="admin-page"><header className="admin-header"><div><h1>Módulo predictivo</h1><p>El visor predictivo sólo está disponible en el entorno local de investigación (npm run dev).</p></div><div><Link className="secondary-button" to="/admin/reportes">Volver a Administración</Link></div></header></main>
  if (!active) return <AdminLoginForm key={token || 'no-session'} title="Módulo predictivo" description="Acceso restringido a cuentas de Administración. Reconstrucción histórica experimental, no uso operativo." notice={notice} onLogin={value => { clearBacktestCache(); setToken(value); setNotice(adminSessionActive(value) ? SESSION_REQUIRED : ROLE_REQUIRED) }}/>

  return <main><div className="content-wrap">
    <nav className="admin-predictive-bar" aria-label="Administración"><Link className="secondary-button" to="/admin/reportes">Volver a Administración</Link><button className="text-button" type="button" onClick={() => leave(SESSION_REQUIRED)}>Cerrar sesión</button></nav>
    <PageIntro title="Predicción semanal de dengue por radio censal"><p>Elegí una semana y mirá dónde y cuántos registros se esperaban, comparados con lo que ocurrió.</p><p className="pv-badge">Prototipo experimental — reconstrucción histórica, no uso operativo</p></PageIntro>
    <HistoricalBacktest onSessionError={leave} />
  </div></main>
}
