import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AdminLayout, { Icon } from '../components/AdminLayout'
import AdminLoginForm from '../components/AdminLoginForm'
import { countText, EXPERIMENTAL_LABEL, formatReceived, integrityText, loaded, modelsText, NOT_AVAILABLE, oldestReportPages, PENDING_LIMIT, pendingItems, publicMapText } from '../services/adminHome.mjs'
import { ADMIN_SECTIONS, environmentLabel, visibleSections } from '../services/adminShell.mjs'
import { adminSessionActive, endSession, readSession, sessionExpired } from '../services/adminSession.mjs'
import { loadDataWeek } from '../services/adminWeek'
import { backtestCalendar } from '../services/backtestResults'
import { alertsRequest, listAdminReports, listPreventionSections } from '../services/citizenReports'
import { demoMode } from '../services/demoMode'
import { localResearchEnabled } from '../services/experimentalResults'
import { MINIMUM_COUNT } from '../services/internalAlerts.mjs'
import { loadActivity } from '../services/publicActivity.mjs'
import '../components/AdminInicio.css'
import '../Prevention.css'

const EXPIRED = 'La sesión venció. Ingresá nuevamente.'
const REVOKED = 'La sesión venció, fue revocada o ya no tiene permisos. Ingresá nuevamente.'
const path = key => ADMIN_SECTIONS.find(section => section.key === key).icon
const ICONS = {
  alerta: path('alertas'), reporte: path('reportes'), contenido: path('contenido'),
  datos: 'M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM3 9h18M8 2v4M16 2v4',
  modelos: 'M9 3h6M10 3v6L4 19a1 1 0 0 0 .9 1.5h14.2A1 1 0 0 0 20 19l-6-10V3',
  integridad: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM8.5 12l2.5 2.5 4.5-5',
  divulgacion: 'M6 10h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2zM8 10V7a4 4 0 0 1 8 0v3',
  mapa: path('predictivo'),
  entorno: 'M4 5h16v11H4zM8 20h8M12 16v4',
}
const KIND_LABELS = { alerta: 'Alerta', reporte: 'Reporte', contenido: 'Contenido' }
const MOBILE_PENDING = 5

// Loads the three «Requiere tu atención» sources from the existing admin APIs. A 401/403 ends the
// session; any other failure leaves that source as «No disponible».
function useAttention(token, mode, onSessionError) {
  const [sources, setSources] = useState(() => ({ alerts: { status: mode.demo ? 'absent' : 'loading' }, reports: { status: 'loading' }, content: { status: 'loading' } }))
  useEffect(() => {
    const controller = new AbortController(), signal = controller.signal
    const settle = (key, request) => request
      .then(value => { if (!signal.aborted) setSources(current => ({ ...current, [key]: { status: 'ok', ...value } })) })
      .catch(error => {
        if (signal.aborted) return
        if (error.status === 401 || error.status === 403) onSessionError(REVOKED)
        else setSources(current => ({ ...current, [key]: { status: 'error' } }))
      })
    if (!mode.demo) settle('alerts', alertsRequest(token, '/candidates?status=pending', { signal }).then(items => {
      if (!Array.isArray(items)) throw new Error('Respuesta inesperada')
      return { count: items.length, items }
    }))
    settle('reports', (async () => {
      const query = { status: 'recibido', page_size: String(PENDING_LIMIT) }
      const first = await listAdminReports(token, query, { signal })
      if (!Number.isInteger(first?.total) || !Array.isArray(first.items)) throw new Error('Respuesta inesperada')
      const pages = oldestReportPages(first.total)
      const rest = await Promise.all(pages.map(page => listAdminReports(token, { ...query, page: String(page) }, { signal })))
      return { count: first.total, items: pages.length ? rest.flatMap(page => page.items || []) : first.items }
    })())
    settle('content', listPreventionSections(token, { signal }).then(sections => {
      if (!Array.isArray(sections)) throw new Error('Respuesta inesperada')
      const items = sections.filter(section => section.has_pending_changes === true)
      return { count: items.length, items }
    }))
    return () => controller.abort()
  }, [token, mode.demo, onSessionError])
  return sources
}

// «Estado del sistema»: the week of the menu, the viewer catalog (models, integrity) and the
// public activity probe. Without the viewer (production, demo) its rows say «No disponible».
function useSystem(viewer, onSessionError) {
  const [state, setState] = useState({ week: undefined, catalog: null, catalogError: null, activity: { status: 'loading' } })
  useEffect(() => {
    let alive = true
    const set = value => { if (alive) setState(current => ({ ...current, ...value })) }
    loadDataWeek(viewer).then(week => set({ week }))
    if (viewer) backtestCalendar().then(catalog => set({ catalog }), error => {
      if (error.session) onSessionError(error.message)
      else set({ catalogError: error })
    })
    loadActivity().then(result => set({ activity: result }))
    return () => { alive = false }
  }, [viewer, onSessionError])
  return state
}

function Attention({ icon, tone, title, chip, text, source, action, href, primary }) {
  const value = countText(source)
  const known = loaded(source)
  return <div className="home-attention-row" data-source={source.status}>
    <span className={`home-icon home-tone-${tone}`}><Icon d={icon} size={22}/></span>
    <div className="home-attention-text">
      <span className="home-attention-title"><strong>{title}</strong>{chip && known && source.count > 0 && <span className="home-chip home-tone-alerta">{chip}</span>}</span>
      <span>{text}</span>
    </div>
    <span className={`home-count${known ? ' mono' : ' home-count-missing'}${tone === 'alerta' && known && source.count > 0 ? ' home-count-urgent' : ''}`} data-count={known ? source.count : ''}>{value}</span>
    {href && <Link className={primary ? 'home-button home-button-primary' : 'home-button'} to={href}>{action}</Link>}
  </div>
}

function Status({ icon, tone, title, children, name }) {
  return <div className="home-status-row" data-status={name}>
    <span className={`home-status-icon home-tone-${tone}`}><Icon d={icon} size={20}/></span>
    <span><strong>{title}</strong><span>{children}</span></span>
  </div>
}

// Administración v2 · Inicio (F5): what needs a decision today and the state of the system,
// following docs/diseno/admin-v2/Main.dc.html. Same session rules as the other screens.
export default function AdminInicio() {
  const [token, setToken] = useState(() => { const stored = readSession(); return stored && !sessionExpired(stored) ? stored : '' })
  const [notice, setNotice] = useState(() => readSession() && !token ? EXPIRED : '')
  useEffect(() => { if (!token && readSession()) endSession() }, [token])
  const leave = useCallback(message => { endSession(); setToken(''); setNotice(message) }, [])
  if (!token) return <AdminLoginForm title="Administración" description="Acceso restringido a personal autorizado." notice={notice} onLogin={value => { setNotice(''); setToken(value) }}/>
  return <AdminLayout active="inicio" token={token} onLogout={() => leave('')} onExpire={() => leave(EXPIRED)}>
    <HomeContent key={token} token={token} onSessionError={leave}/>
  </AdminLayout>
}

function HomeContent({ token, onSessionError }) {
  const mode = { demo: demoMode, localResearch: localResearchEnabled(), dev: import.meta.env.DEV }
  const viewer = mode.localResearch && adminSessionActive(token)
  const sections = new Set(visibleSections(mode).map(section => section.key))
  const [expanded, setExpanded] = useState(false)
  const sources = useAttention(token, mode, onSessionError)
  const system = useSystem(viewer, onSessionError)
  const items = pendingItems(sources)
  const shown = items.slice(0, PENDING_LIMIT)
  // Total from the APIs' counts (reports are fetched only up to the oldest page or two).
  const total = Object.values(sources).filter(loaded).reduce((sum, source) => sum + source.count, 0)
  const failed = [['alerts', 'alertas'], ['reports', 'reportes'], ['content', 'contenido']].filter(([key]) => sources[key].status === 'error').map(([, label]) => label)
  const loading = Object.values(sources).some(source => source.status === 'loading')
  const week = system.week
  const viewerLink = viewer && week?.year ? `/admin/predictivo?anio=${week.year}&se=${week.week}` : '/admin/predictivo'

  return <main className="admin-page admin-home">
    <header className="admin-header home-header">
      <div><h1>Inicio</h1><p>Lo que requiere una decisión hoy y el estado del sistema.</p></div>
      <div><span className="home-badge">{EXPERIMENTAL_LABEL}</span></div>
    </header>

    <div className="home-grid">
      <section className="home-card home-attention" aria-labelledby="home-atencion">
        <h2 id="home-atencion">Requiere tu atención</h2>
        <Attention icon={ICONS.alerta} tone="alerta" title="Alertas candidatas sin revisar" chip="Requiere decisión" source={sources.alerts}
          text={mode.demo ? 'Las alertas internas no existen en la demo ficticia.' : 'Generadas por reglas sobre las predicciones. Ninguna se publica sin tu decisión.'}
          action="Revisar alertas" href={sections.has('alertas') ? '/admin/alertas' : null} primary/>
        <Attention icon={ICONS.reporte} tone="reporte" title="Reportes ciudadanos nuevos" source={sources.reports}
          text="Posibles criaderos informados por la ciudadanía, todavía sin revisar. La ubicación es privada." action="Abrir bandeja" href="/admin/reportes"/>
        <Attention icon={ICONS.contenido} tone="contenido" title="Contenido con cambios sin publicar" source={sources.content}
          text="Secciones preventivas editadas que todavía no ve la ciudadanía." action="Ir a contenido" href="/admin/contenido"/>
      </section>

      <section className="home-card home-status" aria-labelledby="home-estado">
        <h2 id="home-estado">Estado del sistema</h2>
        <Status name="datos" icon={ICONS.datos} tone="ok" title="Datos epidemiológicos">
          {week === undefined ? 'Cargando…' : week ? <>Disponibles hasta <span className="mono mono-week" title={`Hasta el ${week.date.split('-').reverse().join('/')} (${week.source})`}>{week.label}</span></> : NOT_AVAILABLE}
        </Status>
        <Status name="modelos" icon={ICONS.modelos} tone="warn" title="Modelos">
          {viewer ? (system.catalog ? modelsText(system.catalog) : system.catalogError ? NOT_AVAILABLE : 'Cargando…') : `${NOT_AVAILABLE} · sin visor predictivo en este entorno`}
        </Status>
        <Status name="integridad" icon={ICONS.integridad} tone="ok" title="Integridad de paquetes">
          {integrityText({ viewer, catalog: system.catalog, error: system.catalogError })}
        </Status>
        <Status name="divulgacion" icon={ICONS.divulgacion} tone="ok" title="Divulgación">Modo protegido · valores menores a {MINIMUM_COUNT} ocultos</Status>
        <Status name="mapa" icon={ICONS.mapa} tone="neutral" title="Mapa público con datos reales">{publicMapText(system.activity)}</Status>
        <Status name="entorno" icon={ICONS.entorno} tone="neutral" title="Entorno">{environmentLabel(mode)}</Status>
      </section>
    </div>

    <section className="home-card home-pending" aria-labelledby="home-pendientes" aria-busy={loading}>
      <h2 id="home-pendientes">Pendientes, del más antiguo al más reciente</h2>
      {failed.length > 0 && <p className="home-note" role="status">No disponible: no se pudieron cargar los pendientes de {failed.join(', ')}.</p>}
      {loading && <p className="home-note" role="status">Cargando pendientes…</p>}
      {!loading && !items.length && !failed.length && <p className="home-note" role="status">No hay pendientes.</p>}
      {shown.length > 0 && <table className={`home-table${expanded ? ' expanded' : ''}`} id="home-pending-table">
        <thead><tr><th scope="col">Tipo</th><th scope="col">Detalle</th><th scope="col">Recibido</th><th scope="col"><span className="home-sr">Acción</span></th></tr></thead>
        <tbody>{shown.map((item, index) => <tr key={item.id} data-kind={item.kind} className={index >= MOBILE_PENDING ? 'home-extra' : undefined}>
          <td><span className={`home-chip home-tone-${item.kind}`}><Icon d={ICONS[item.kind]} size={14}/>{KIND_LABELS[item.kind]}</span></td>
          <td>{item.detail.join(' · ')}</td>
          <td className="home-date"><time dateTime={item.date}>{formatReceived(item.date)}</time></td>
          <td><Link to={item.href} aria-label={`Revisar ${KIND_LABELS[item.kind].toLowerCase()}: ${item.detail.join(' · ')}`}>Revisar</Link></td>
        </tr>)}</tbody>
      </table>}
      {/* Narrow screens list the 5 oldest first; «Ver más» shows the rest of the 10. */}
      {shown.length > MOBILE_PENDING && <button type="button" className="home-more" aria-expanded={expanded} aria-controls="home-pending-table" onClick={() => setExpanded(value => !value)}>{expanded ? 'Ver menos' : 'Ver más'}</button>}
      {total > shown.length && shown.length > 0 && <p className="home-note">Se muestran los {shown.length} más antiguos de {total}. El resto está en cada sección.</p>}
    </section>

    <section className="home-quick" aria-labelledby="home-rapidos">
      <h2 id="home-rapidos">Accesos rápidos</h2>
      <div>
        {sections.has('predictivo') && <Link className="home-button home-button-primary" to={viewerLink}>{viewer && week?.year ? `Abrir el visor en ${week.label}` : 'Abrir el visor predictivo'}</Link>}
        {sections.has('alertas') && <Link className="home-button" to="/admin/alertas">Reglas de alerta</Link>}
        <Link className="home-button" to="/admin/reportes">Exportar reportes (CSV)</Link>
        <Link className="home-button" to="/admin/contenido">Nueva sección preventiva</Link>
      </div>
    </section>
  </main>
}
