import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import AdminLayout from '../components/AdminLayout'
import AdminLoginForm from '../components/AdminLoginForm'
import { Badge, Card, Notice, ScreenHeader, UiButton, UiTable } from '../components/AdminUI'
import { ACTIONS, AUDIT_PAGE_SIZE, CATEGORIES, LOCAL_ONLY_NOTICE, PRIVACY_NOTICE, actionLabel, apiQuery, argentinaDateTime, detailText,
  filtersFromSearch, objectText, searchFromFilters } from '../services/adminAudit.mjs'
import { endSession, readSession, sessionExpired } from '../services/adminSession.mjs'
import { listAdminAccounts, listAdminAudit } from '../services/citizenReports'
import { localResearchEnabled } from '../services/experimentalResults'
import './AdminAuditoria.css'

// F6.6: read-only audit trail. The API exists only on the local administrative API (npm run dev);
// the demo and production show a notice instead of querying it. Filters and page live in the URL.
const EXPIRED = 'La sesión venció. Ingresá nuevamente.'
const REVOKED = 'La sesión venció, fue revocada o ya no tiene permisos. Ingresá nuevamente.'
const ICONS = {
  cuentas: 'M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21c0-4 3-6 7-6s7 2 7 6',
  reportes: 'M4 4h16v12H5.2L4 17.2zM8 9h8M8 12h5',
  contenido: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z',
  alertas: 'M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0',
  visor: 'M9 4L3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14',
  auditoria: 'M9 4h6l1 3h4v13H4V7h4zM8 13l3 3 5-5',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01',
}
// Long addresses break only before the «@» (<wbr> adds no text).
const emailText = email => { const at = email.indexOf('@'); return at > 0 ? <>{email.slice(0, at)}<wbr/>{email.slice(at)}</> : email }
const TONES = { cuentas: 'neutral', reportes: 'info', contenido: 'ok', alertas: 'warn', visor: 'alert', auditoria: 'neutral' }

export default function AdminAuditoria() {
  const [token, setToken] = useState(() => { const stored = readSession(); return stored && !sessionExpired(stored) ? stored : '' })
  const [notice, setNotice] = useState(() => readSession() && !token ? EXPIRED : '')
  useEffect(() => { if (!token && readSession()) endSession() }, [token])
  const leave = useCallback(message => { endSession(); setToken(''); setNotice(message) }, [])
  if (!token) return <AdminLoginForm title="Administración" description="Acceso restringido a personal autorizado." notice={notice} onLogin={value => { setNotice(''); setToken(value) }}/>
  return <AdminLayout active="auditoria" token={token} onLogout={() => leave('')} onExpire={() => leave(EXPIRED)}>
    <AuditContent key={token} token={token} onSessionError={leave}/>
  </AdminLayout>
}

function AuditContent({ token, onSessionError }) {
  const local = localResearchEnabled()
  return <main className="admin-page admin-auditoria">
    <ScreenHeader breadcrumb={[{ label: 'Inicio', to: '/admin/inicio' }, { label: 'Auditoría' }]} title="Auditoría"
      subtitle="Registro de acciones administrativas. Sólo lectura."/>
    {local ? <AuditTrail token={token} onSessionError={onSessionError}/>
      : <Notice tone="info" icon={ICONS.info} className="audit-local-only"><p>{LOCAL_ONLY_NOTICE}</p></Notice>}
  </main>
}

function AuditTrail({ token, onSessionError }) {
  const [params, setParams] = useSearchParams()
  const filters = filtersFromSearch(params)
  const query = apiQuery(filters)
  const [result, setResult] = useState({ query: '', data: null, error: '' })
  const [attempt, setAttempt] = useState(0)
  const [accounts, setAccounts] = useState([])
  const invalidDates = Boolean(filters.from && filters.to && filters.from > filters.to)
  const loading = !invalidDates && result.query !== `${query}#${attempt}`
  const data = loading ? null : result.data
  const error = loading ? '' : result.error

  useEffect(() => {
    if (invalidDates) return undefined
    const controller = new AbortController(), key = `${query}#${attempt}`
    listAdminAudit(token, query, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setResult({ query: key, data: value, error: '' }) })
      .catch(requestError => {
        if (controller.signal.aborted) return
        if (requestError.status === 401 || requestError.status === 403) onSessionError(REVOKED)
        else setResult({ query: key, data: null, error: requestError.message })
      })
    return () => controller.abort()
  }, [attempt, invalidDates, onSessionError, query, token])
  useEffect(() => {
    let alive = true
    listAdminAccounts(token).then(page => { if (alive && Array.isArray(page?.items)) setAccounts(page.items) }).catch(() => {})
    return () => { alive = false }
  }, [token])

  const change = next => setParams(searchFromFilters({ ...filters, ...next, page: next.page ?? 1 }))
  const pages = data ? Math.max(1, Math.ceil(data.total / AUDIT_PAGE_SIZE)) : 1

  return <>
    <Notice tone="warn" className="audit-private"><p>{PRIVACY_NOTICE}</p></Notice>
    <Card as="div" className="audit-filters">
      <fieldset aria-label="Filtros">
        <label htmlFor="audit-category">Categoría<select id="audit-category" value={filters.category} onChange={event => change({ category: event.target.value, action: '' })}>
          <option value="">Todas</option>
          {Object.entries(CATEGORIES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label htmlFor="audit-action">Acción<select id="audit-action" value={filters.action} disabled={!filters.category} onChange={event => change({ action: event.target.value })}>
          <option value="">Todas</option>
          {filters.category && Object.entries(ACTIONS[filters.category]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label htmlFor="audit-actor">Usuario<select id="audit-actor" value={filters.actor} onChange={event => change({ actor: event.target.value })}>
          <option value="">Todos</option>
          {accounts.map(account => <option key={account.id} value={String(account.id)}>{account.email}</option>)}
        </select></label>
        <label htmlFor="audit-from">Desde<input id="audit-from" type="date" value={filters.from} onChange={event => change({ from: event.target.value })}/></label>
        <label htmlFor="audit-to">Hasta<input id="audit-to" type="date" value={filters.to} onChange={event => change({ to: event.target.value })}/></label>
        <UiButton className="audit-clear" onClick={() => setParams(new URLSearchParams())}>Limpiar filtros</UiButton>
      </fieldset>
      <small className="audit-zone">«Todas» no incluye las consultas a esta pantalla (categoría «Auditoría»). La acción se elige después de la categoría. Fechas y horas de Argentina (UTC−3); «Hasta» incluye el día completo.</small>
    </Card>
    {invalidDates ? <Notice tone="danger" icon={null} role="alert" className="form-error"><p>La fecha Desde no puede ser posterior a Hasta.</p></Notice>
      : error && <Notice tone="danger" icon={null} role="alert" className="form-error"><p>{error}</p><UiButton onClick={() => setAttempt(value => value + 1)}>Reintentar</UiButton></Notice>}
    <Card className="audit-results" title="Eventos" titleId="audit-results-title" aria-busy={loading}>
      {loading && <p role="status">Consultando la auditoría…</p>}
      {data && <p className="audit-count">{data.total} {data.total === 1 ? 'evento' : 'eventos'}</p>}
      {invalidDates && <p className="audit-empty">Corregí el rango de fechas para consultar.</p>}
      {data && !data.items.length && <p className="audit-empty" role="status">No hay eventos para estos filtros.</p>}
      {data && data.items.length > 0 && <UiTable className="audit-table" aria-labelledby="audit-results-title">
        <thead><tr><th scope="col">Fecha y hora</th><th scope="col">Categoría</th><th scope="col">Acción</th><th scope="col">Usuario</th><th scope="col">Objeto</th><th scope="col">Detalle</th></tr></thead>
        <tbody>{data.items.map(event => <tr key={event.id} data-category={event.category}>
          <td><time className="mono" dateTime={event.created_at}>{argentinaDateTime(event.created_at)}</time></td>
          <td><Badge tone={TONES[event.category] || 'neutral'} icon={ICONS[event.category]} className="audit-category">{CATEGORIES[event.category] || event.category}</Badge></td>
          <td className="audit-action">{actionLabel(event)}</td>
          <td className="audit-actor">{event.actor ? (event.actor.email ? emailText(event.actor.email) : `Usuario ${event.actor.id}`) : 'Sistema'}</td>
          <td className="audit-object">{objectText(event)}</td>
          <td className="audit-detail">{detailText(event)}</td>
        </tr>)}</tbody>
      </UiTable>}
      {data && data.total > 0 && <div className="audit-pagination">
        <UiButton disabled={filters.page <= 1} onClick={() => change({ page: filters.page - 1 })}>Anterior</UiButton>
        <span>Página <span className="mono">{filters.page}</span> de <span className="mono">{pages}</span></span>
        <UiButton disabled={filters.page >= pages} onClick={() => change({ page: filters.page + 1 })}>Siguiente</UiButton>
      </div>}
    </Card>
  </>
}
