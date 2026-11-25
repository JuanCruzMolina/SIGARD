import { useCallback, useContext, useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { ADMIN_GROUPS, environmentLabel, minutesLeft, visibleSections } from '../services/adminShell.mjs'
import { adminSessionActive, endSession, readEmail, sessionRemaining } from '../services/adminSession.mjs'
import { loadDataWeek } from '../services/adminWeek'
import { alertsRequest, listAdminReports } from '../services/citizenReports'
import { demoMode } from '../services/demoMode'
import { localResearchEnabled } from '../services/experimentalResults'
import { AdminCountersContext, AdminFrameContext } from './adminFrame'
import './AdminLayout.css'

// Counters only from numbers the API already returns; any failure means "no number".
function useCounters(token, refreshKey, mode) {
  const [counters, setCounters] = useState({})
  useEffect(() => {
    if (!token) return undefined
    const controller = new AbortController(), signal = controller.signal
    const count = (key, request) => request.then(value => { if (!signal.aborted) setCounters(current => ({ ...current, [key]: value })) })
      .catch(() => { if (!signal.aborted) setCounters(current => ({ ...current, [key]: null })) })
    if (!mode.demo) count('alertas', alertsRequest(token, '/status', { signal }).then(status => Number.isInteger(status?.pending) ? status.pending : null))
    count('reportes', listAdminReports(token, { status: 'recibido', page_size: '1' }, { signal }).then(page => Number.isInteger(page?.total) ? page.total : null))
    return () => controller.abort()
  }, [token, refreshKey, mode.demo])
  return counters
}

export function Icon({ d, size = 18 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={d}/></svg>
}

const LOCK = 'M6 10h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2zM8 10V7a4 4 0 0 1 8 0v3'
const MENU = 'M4 6h16M4 12h16M4 18h16'

// Administración v2 frame: side menu (top, collapsible, on narrow screens) and top bar.
// It wraps the existing screens without changing their content.
// onExpire runs when the token's exp is reached (default: onLogout); token and email are removed first.
// The counters are asked again when the section changes, when a screen inside calls the
// AdminCountersContext function, or when the owner of the frame changes countersVersion.
export default function AdminLayout({ active, token, onLogout, onExpire, countersVersion: ownerVersion = 0, children }) {
  const setFrame = useContext(AdminFrameContext)
  const mode = { demo: demoMode, localResearch: localResearchEnabled(), dev: import.meta.env.DEV }
  const [open, setOpen] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const [week, setWeek] = useState(null)
  const [countersVersion, setCountersVersion] = useState(0)
  const refreshCounters = useCallback(() => setCountersVersion(value => value + 1), [])
  const counters = useCounters(token, `${active}:${ownerVersion}:${countersVersion}`, mode)
  const email = readEmail()
  const minutes = minutesLeft(sessionRemaining(token, now))

  useEffect(() => { setFrame(true); return () => setFrame(false) }, [setFrame])
  const viewerWeek = mode.localResearch && adminSessionActive(token)
  useEffect(() => {
    let alive = true
    ;loadDataWeek(viewerWeek).then(value => { if (alive) setWeek(value) })
    return () => { alive = false }
  }, [viewerWeek])
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(timer) }, [])
  // Session expiry inside any section: clear the stored token and email at exp, then hand over.
  useEffect(() => {
    const expire = () => { endSession(); (onExpire || onLogout)?.() }
    const timer = setTimeout(expire, Math.min(sessionRemaining(token), 2 ** 31 - 1))
    return () => clearTimeout(timer)
  }, [token, onExpire, onLogout])

  const sections = visibleSections(mode)
  return <div className="admin-shell">
    <nav className="admin-nav" aria-label="Área de administración"><div className="admin-nav-inner">
      <div className="admin-nav-head">
        <span className="admin-brand"><span className="admin-brand-mark" aria-hidden="true">S</span><span><strong>SIGARD</strong><small>Administración</small></span></span>
        <button type="button" className="admin-nav-toggle" aria-expanded={open} aria-controls="admin-nav-items" onClick={() => setOpen(value => !value)}><Icon d={MENU} size={20}/><span>Menú</span></button>
      </div>
      <div id="admin-nav-items" className={`admin-nav-items${open ? ' open' : ''}`}>
        {ADMIN_GROUPS.map(group => <div className="admin-nav-group" key={group.key} role="group" aria-labelledby={`admin-nav-${group.key}`}>
          <span className="admin-nav-group-title" id={`admin-nav-${group.key}`}>{group.label}</span>
          {sections.filter(section => section.group === group.key).map(section => {
            const value = counters[section.key]
            return <NavLink key={section.key} to={section.path} className="admin-nav-item" onClick={() => setOpen(false)}>
              <Icon d={section.icon}/><span>{section.label}</span>
              {Number.isInteger(value) && value > 0 && <span className="admin-nav-badge" aria-label={`${value} ${section.key === 'alertas' ? 'pendientes de revisión' : 'recibidos sin revisar'}`}>{value}</span>}
            </NavLink>
          })}
        </div>)}
        <dl className="admin-context" aria-label="Contexto de los datos">
          <div><dt>Entorno</dt><dd>{environmentLabel(mode)}</dd></div>
          <div><dt>Divulgación</dt><dd>Protegida</dd></div>
          <div><dt>Datos hasta</dt><dd className="mono mono-week" data-week={week?.date || ''} data-week-source={week?.source || ''} title={week ? `Hasta el ${week.date.split('-').reverse().join('/')} (${week.source})` : undefined}>{week ? week.label : '—'}</dd></div>
        </dl>
        {/* Narrow screens: «Cerrar sesión» closes the drop-down menu (the top bar keeps one line). */}
        <button type="button" className="admin-nav-logout" onClick={onLogout}>Cerrar sesión</button>
      </div>
    </div></nav>
    <div className="admin-frame">
      <header className="admin-topbar">
        <span className="admin-restricted"><Icon d={LOCK} size={16}/><span className="admin-compact-hide">Área con acceso restringido</span></span>
        <div className="admin-session">
          <span className="admin-expiry"><span className="admin-compact-hide">Sesión: </span>vence en <span className="mono">{minutes}</span> min</span>
          {email && <span className="admin-email" title={email}>{email}</span>}
          <button type="button" className="admin-logout" onClick={onLogout}>Cerrar sesión</button>
        </div>
      </header>
      <div className="admin-content"><AdminCountersContext.Provider value={refreshCounters}>{children}</AdminCountersContext.Provider></div>
    </div>
  </div>
}
