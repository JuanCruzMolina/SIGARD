import { useContext, useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { ADMIN_GROUPS, environmentLabel, epiWeekLabel, minutesLeft, visibleSections } from '../services/adminShell.mjs'
import { adminSessionActive, endSession, readEmail, sessionRemaining } from '../services/adminSession.mjs'
import { backtestCalendar } from '../services/backtestResults'
import { lastEvaluableWeek } from '../services/predictiveView.mjs'
import { alertsRequest, listAdminReports } from '../services/citizenReports'
import { demoMode } from '../services/demoMode'
import { localResearchEnabled } from '../services/experimentalResults'
import { AdminFrameContext } from './adminFrame'
import './AdminLayout.css'

// «Datos hasta» (never hand-written). Where the predictive viewer exists (local research with an
// administrator session) it is the viewer's last evaluable week, read from the same /calendar the
// viewer uses (shared cache), with the API's own SE/year. Elsewhere there is no viewer: the week of
// the public weeks manifest (/data/available_weeks.json) is shown and the tooltip says so.
let manifestWeek
function loadManifestWeek() {
  manifestWeek ||= fetch('/data/available_weeks.json', { cache: 'no-store' })
    .then(response => response.ok ? response.json() : null)
    .then(manifest => manifest?.default_cutoff_date ? { label: epiWeekLabel(manifest.default_cutoff_date), date: manifest.default_cutoff_date, source: 'manifiesto de semanas publicado' } : null)
    .catch(() => null)
  return manifestWeek
}
function loadViewerWeek() {
  return backtestCalendar().then(catalog => {
    const last = lastEvaluableWeek(catalog.weeks)
    return last ? { label: `SE ${last.target_epi_week}/${last.target_year}`, date: last.target_end, source: 'última semana evaluable del visor predictivo' } : null
  }).catch(() => null)
}

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

function Icon({ d, size = 18 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={d}/></svg>
}

const LOCK = 'M6 10h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2zM8 10V7a4 4 0 0 1 8 0v3'
const MENU = 'M4 6h16M4 12h16M4 18h16'

// Administración v2 frame: side menu (top, collapsible, on narrow screens) and top bar.
// It wraps the existing screens without changing their content.
// onExpire runs when the token's exp is reached (default: onLogout); token and email are removed first.
export default function AdminLayout({ active, token, onLogout, onExpire, children }) {
  const setFrame = useContext(AdminFrameContext)
  const mode = { demo: demoMode, localResearch: localResearchEnabled(), dev: import.meta.env.DEV }
  const [open, setOpen] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const [week, setWeek] = useState(null)
  const counters = useCounters(token, active, mode)
  const email = readEmail()
  const minutes = minutesLeft(sessionRemaining(token, now))

  useEffect(() => { setFrame(true); return () => setFrame(false) }, [setFrame])
  const viewerWeek = mode.localResearch && adminSessionActive(token)
  useEffect(() => {
    let alive = true
    ;(viewerWeek ? loadViewerWeek() : loadManifestWeek()).then(value => { if (alive) setWeek(value) })
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
          <div><dt>Datos hasta</dt><dd className="mono" data-week={week?.date || ''} data-week-source={week?.source || ''} title={week ? `Hasta el ${week.date.split('-').reverse().join('/')} (${week.source})` : undefined}>{week ? week.label : '—'}</dd></div>
        </dl>
      </div>
    </div></nav>
    <div className="admin-frame">
      <header className="admin-topbar">
        <span className="admin-restricted"><Icon d={LOCK} size={16}/>Área con acceso restringido</span>
        <div className="admin-session">
          <span>Sesión: vence en <span className="mono">{minutes}</span> min</span>
          {email && <span className="admin-email">{email}</span>}
          <button type="button" className="admin-logout" onClick={onLogout}>Cerrar sesión</button>
        </div>
      </header>
      <div className="admin-content">{children}</div>
    </div>
  </div>
}
