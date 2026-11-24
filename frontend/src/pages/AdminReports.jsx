import { useCallback, useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { GeoJSON, MapContainer, Marker } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { PinIcon, ShieldIcon } from '../components/InfoIcons'
import AdminLayout, { Icon } from '../components/AdminLayout'
import { Badge, Card, Notice, ScreenHeader, UiButton, UiTable } from '../components/AdminUI'
import AdminLoginForm from '../components/AdminLoginForm'
import AdminAccounts from '../components/AdminAccounts'
import AdminAlerts from '../components/AdminAlerts'
import AdminPrevention from '../components/AdminPrevention'
import DemoWorkspace from '../components/DemoWorkspace'
import { demoMode } from '../services/demoMode'
import { endSession, readSession } from '../services/adminSession.mjs'
import { REPORT_CATEGORY_LABELS as categoryLabels } from '../services/citizenReportValidation.mjs'
import {
  downloadAdminExport,
  getAdminReport,
  listAdminReports,
  updateAdminReport,
} from '../services/citizenReports'
import '../Prevention.css'
import './AdminReports.css'

const statuses = ['recibido', 'en_revision', 'pendiente_de_derivacion', 'derivado', 'resuelto', 'descartado']
const statusLabels = { recibido: 'Recibido', en_revision: 'En revisión', pendiente_de_derivacion: 'Pendiente de derivación', derivado: 'Derivado', resuelto: 'Resuelto', descartado: 'Descartado' }
const privateIcon = L.divIcon({ className: '', html: '<span class="report-marker private"></span>', iconSize: [32, 38], iconAnchor: [16, 34] })
const emptyFilters = { category: '', status: '', neighborhood: '', date_from: '', date_to: '' }
const emptyListing = { items: [], total: 0, page: 1, page_size: 25 }
// F6.3 (docs/diseno/admin-v2/Reportes.dc.html): presentation only. Statuses, transitions, requests,
// CSV export and texts are the same; the description and exact location load only in the detail.
const ICONS = {
  dot: 'M12 7a5 5 0 1 0 0 10 5 5 0 1 0 0-10z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  hourglass: 'M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9s8 4 8 9',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  check: 'M5 12l4 4 10-10',
  cross: 'M6 6l12 12M18 6L6 18',
  lock: 'M6 10h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2zM8 10V7a4 4 0 0 1 8 0v3',
  warning: 'M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
}
const STATUS_STYLE = { recibido: ['alert', ICONS.dot], en_revision: ['info', ICONS.clock], pendiente_de_derivacion: ['warn', ICONS.hourglass], derivado: ['info', ICONS.arrow], resuelto: ['ok', ICONS.check], descartado: ['neutral', ICONS.cross] }
// List and detail stacked (narrow screens): the empty detail is hidden and a chosen report is scrolled into view.
const STACKED = '(max-width: 1199px)'

function StatusBadge({ status }) {
  const [tone, icon] = STATUS_STYLE[status] || ['neutral']
  return <Badge tone={tone} icon={icon} className="report-status">{statusLabels[status] || status}</Badge>
}

function PrivateLocationMap({ report }) {
  const [territorialContext, setTerritorialContext] = useState(null)
  useEffect(() => {
    let active = true
    fetch('/data/territorial_context.geojson')
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (active) setTerritorialContext(data) })
      .catch(() => {})
    return () => { active = false }
  }, [])
  return <div className="private-map"><MapContainer key={report.id} center={[report.latitude, report.longitude]} zoom={14} scrollWheelZoom={false}>{territorialContext && <GeoJSON data={territorialContext} style={{ color: '#88a9a2', weight: 1, fillColor: '#e9f0ec', fillOpacity: .55 }}/>}<Marker position={[report.latitude, report.longitude]} icon={privateIcon} interactive={false} keyboard={false}/></MapContainer><small>Contexto censal local de SIGARD, sin teselas ni servicios cartográficos externos.</small></div>
}

// F4: one screen per /admin/* section (reportes, alertas, contenido, cuentas) inside AdminLayout;
// the menu and the top bar («Cerrar sesión») replace the former header buttons.
export default function AdminReports({ section = 'reportes' }) {
  const [token, setToken] = useState(readSession)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState(emptyFilters)
  const [readyFilters, setReadyFilters] = useState(emptyFilters)
  const [listResult, setListResult] = useState({ key: '', data: emptyListing, error: '' })
  const [refresh, setRefresh] = useState(0)
  const [selected, setSelected] = useState(null)
  const [changes, setChanges] = useState({ status: '', public_status_message: '', internal_notes: '', possible_duplicate_of: '' })
  const [error, setError] = useState('')
  const [panel, setPanel] = useState('reports')
  const [sessionNotice, setSessionNotice] = useState('')
  const [detailLoading, setDetailLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [countersVersion, setCountersVersion] = useState(0)
  const requests = useRef({})
  const detailRef = useRef(null)
  const invalidDates = filters.date_from && filters.date_to && filters.date_from > filters.date_to
  const requestKey = JSON.stringify({ token, filters, page, refresh })
  const listLoading = Boolean(token && !invalidDates && listResult.key !== requestKey)
  const listing = listResult.key === requestKey ? listResult.data : emptyListing
  const listError = invalidDates ? 'La fecha Desde no puede ser posterior a Hasta.' : listResult.key === requestKey ? listResult.error : ''
  const beginRequest = useCallback((kind) => {
    requests.current[kind]?.abort()
    const request = new AbortController()
    requests.current[kind] = request
    return request
  }, [])
  const cancelRequests = useCallback(() => { Object.values(requests.current).forEach(request => request?.abort()) }, [])
  useEffect(() => cancelRequests, [cancelRequests])
  useEffect(() => {
    const timer = setTimeout(() => setReadyFilters(filters), 250)
    return () => clearTimeout(timer)
  }, [filters])

  const logout = useCallback(() => { cancelRequests(); endSession(); setToken(''); setSelected(null); setListResult({ key: '', data: emptyListing, error: '' }); setPage(1); setFilters(emptyFilters); setSaving(false); setExporting(false); setDetailLoading(false); setChanges({ status: '', public_status_message: '', internal_notes: '', possible_duplicate_of: '' }); setPanel('reports'); setSessionNotice(''); setError('') }, [cancelRequests])
  const sessionExpired = useCallback((message) => { logout(); setError(''); setSessionNotice(message) }, [logout])
  const handleRequestError = useCallback((requestError) => {
    if (requestError.status === 401 || requestError.status === 403) sessionExpired('La sesión venció, fue revocada o ya no tiene permisos. Ingresá nuevamente.')
    else setError(requestError.message)
  }, [sessionExpired])
  const loadList = () => setRefresh(value => value + 1)

  useEffect(() => {
    if (!token || section !== 'reportes' || panel !== 'reports' || invalidDates || filters !== readyFilters) return undefined
    const request = beginRequest('list')
    listAdminReports(token, { ...filters, page: String(page) }, { signal: request.signal })
      .then((data) => { if (!request.signal.aborted) setListResult({ key: requestKey, data, error: '' }) })
      .catch((requestError) => {
        if (request.signal.aborted) return
        if (requestError.status === 401 || requestError.status === 403) handleRequestError(requestError)
        else setListResult({ key: requestKey, data: emptyListing, error: requestError.message })
      })
    return () => request.abort()
  }, [beginRequest, filters, handleRequestError, invalidDates, page, panel, readyFilters, requestKey, section, token])

  function changeFilters(next) {
    requests.current.detail?.abort(); requests.current.export?.abort()
    setSelected(null); setDetailLoading(false); setExporting(false); setError(''); setPage(1); setFilters(next)
  }

  async function selectReport(id) {
    const request = beginRequest('detail')
    setError(''); setSelected(null); setDetailLoading(true)
    try {
      const report = await getAdminReport(token, id, { signal: request.signal })
      if (request.signal.aborted) return
      setSelected(report)
      if (window.matchMedia?.(STACKED).matches) requestAnimationFrame(() => detailRef.current?.scrollIntoView({ block: 'start' }))
      setChanges({ status: report.status, public_status_message: report.public_status_message || '', internal_notes: report.internal_notes || '', possible_duplicate_of: report.possible_duplicate_of || '' })
    } catch (requestError) { if (!request.signal.aborted) handleRequestError(requestError) }
    finally { if (!request.signal.aborted) setDetailLoading(false) }
  }

  async function save(event) {
    event.preventDefault()
    if (requests.current.save && !requests.current.save.signal.aborted) return
    const request = beginRequest('save')
    setSaving(true); setError('')
    try {
      const updated = await updateAdminReport(token, selected.id, changes, { signal: request.signal })
      if (!request.signal.aborted) { setSelected(updated); loadList(); setCountersVersion(value => value + 1) }
    } catch (requestError) { if (!request.signal.aborted) handleRequestError(requestError) }
    finally { if (!request.signal.aborted) setSaving(false); request.abort() }
  }

  async function exportResults() {
    const request = beginRequest('export')
    setExporting(true); setError('')
    try { await downloadAdminExport(token, filters, { signal: request.signal }) }
    catch (requestError) { if (!request.signal.aborted) handleRequestError(requestError) }
    finally { if (!request.signal.aborted) setExporting(false) }
  }

  if (!token) return <AdminLoginForm title="Bandeja de reportes" description="Acceso restringido a personal autorizado. Las ubicaciones y descripciones son privadas." notice={sessionNotice} onLogin={(value) => { setError(''); setSessionNotice(''); setToken(value) }}/>

  const framed = content => <AdminLayout active={section} token={token} countersVersion={countersVersion} onLogout={logout} onExpire={() => sessionExpired('La sesión venció. Ingresá nuevamente.')}>{content}</AdminLayout>
  if (section === 'cuentas') return framed(<AdminAccounts token={token} onSessionExpired={sessionExpired}/>)
  if (section === 'alertas') return framed(demoMode ? <main className="admin-page"><header className="admin-header"><div><h1>Alertas internas</h1><p>En la demo integral las alertas ficticias están en «Análisis y alertas demo» de Reportes ciudadanos.</p></div></header></main> : <AdminAlerts token={token} onSessionExpired={sessionExpired}/>)
  if (section === 'contenido') return framed(<AdminPrevention token={token} onSessionExpired={sessionExpired}/>)

  if (panel === 'demo' && demoMode) return framed(<main className="admin-page"><header className="admin-header"><div><h1>Espacio de análisis territorial</h1><p>Rol administrador · sesión validada por la API · sólo fixtures ficticias.</p></div><div><button className="secondary-button" type="button" onClick={() => { loadList(); setPanel('reports') }}>Volver a reportes</button></div></header><DemoWorkspace token={token} onSessionExpired={sessionExpired}/></main>)

  const received = value => new Date(value).toLocaleString('es-AR')
  const detailEmpty = !detailLoading && !selected
  return framed(<main className="admin-page admin-reports">
    <ScreenHeader breadcrumb={[{ label: 'Inicio', to: '/admin/inicio' }, { label: 'Reportes ciudadanos' }]} title="Reportes ciudadanos"
      subtitle="Operación interna. Estos registros no son casos de dengue ni evidencia epidemiológica."
      aside={<>{demoMode && <UiButton disabled={saving} onClick={() => { cancelRequests(); setSelected(null); setPanel('demo') }}>Análisis y alertas demo</UiButton>}
        <UiButton disabled={exporting || listLoading || saving || Boolean(listError)} onClick={exportResults}>{exporting ? 'Exportando…' : 'Exportar CSV'}</UiButton></>} />
    <Notice tone="warn" icon={ICONS.warning} className="reports-private"><p><strong>Información privada.</strong> No copies coordenadas exactas a mapas públicos ni herramientas analíticas de terceros.</p></Notice>
    <Card as="div" className="reports-filters">
      <fieldset className="admin-filters" disabled={saving} aria-label="Filtros">
        <label>Categoría<select value={filters.category} onChange={(event) => { changeFilters({ ...filters, category: event.target.value }) }}><option value="">Todas</option>{Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Estado<select value={filters.status} onChange={(event) => { changeFilters({ ...filters, status: event.target.value }) }}><option value="">Todos</option>{statuses.map((value) => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></label>
        <label className="reports-filter-wide">Barrio<input value={filters.neighborhood} onChange={(event) => { changeFilters({ ...filters, neighborhood: event.target.value }) }} placeholder="Buscar barrio"/></label>
        <label>Desde<input type="date" value={filters.date_from} onChange={(event) => { changeFilters({ ...filters, date_from: event.target.value }) }}/></label>
        <label>Hasta<input type="date" value={filters.date_to} onChange={(event) => { changeFilters({ ...filters, date_to: event.target.value }) }}/></label>
        <UiButton className="reports-clear" onClick={() => changeFilters(emptyFilters)}>Limpiar filtros</UiButton>
      </fieldset>
    </Card>
    {listError && <Notice tone="danger" icon={null} role="alert" className="form-error admin-error"><p>{listError}</p>{!invalidDates && <UiButton onClick={loadList}>Reintentar listado</UiButton>}</Notice>}
    {error && <Notice tone="danger" icon={null} role="alert" className="form-error admin-error"><p>{error}</p></Notice>}
    <div className="reports-layout">
      <section className="report-inbox ui-card" aria-label="Listado de reportes" aria-busy={listLoading}>
        <header><strong>{listing.total} reportes</strong>{listLoading && <span role="status">Cargando reportes…</span>}</header>
        {!listLoading && !listError && !listing.items.length ? <p className="inbox-empty" role="status">No hay reportes para estos filtros.</p>
          : <UiTable className="reports-table" aria-label="Reportes">
            <thead><tr><th scope="col">Código</th><th scope="col">Tipo</th><th scope="col">Recibido</th><th scope="col">Estado</th></tr></thead>
            <tbody>{listing.items.map((report) => <tr key={report.id} aria-selected={selected?.id === report.id} className={selected?.id === report.id ? 'selected' : undefined}>
              <td><button type="button" className="report-open mono" disabled={saving} aria-pressed={selected?.id === report.id} onClick={() => selectReport(report.id)}>{report.tracking_code}</button></td>
              <td>{categoryLabels[report.category] || report.category}</td>
              <td><time dateTime={report.created_at}>{received(report.created_at)}</time></td>
              <td><StatusBadge status={report.status}/></td>
            </tr>)}</tbody>
          </UiTable>}
        <footer><UiButton disabled={listLoading || saving || page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</UiButton><span>Página <span className="mono">{page}</span></span><UiButton disabled={listLoading || saving || page * listing.page_size >= listing.total} onClick={() => setPage((value) => value + 1)}>Siguiente</UiButton></footer>
      </section>
      <section ref={detailRef} className={detailEmpty ? 'report-detail ui-card report-detail-empty' : 'report-detail ui-card'} aria-labelledby={selected ? 'report-detail-title' : undefined} aria-label={selected ? undefined : 'Detalle del reporte'} aria-busy={detailLoading || saving}>
        {detailLoading ? <p role="status">Cargando detalle del reporte…</p> : selected ? <>
          <header>
            <h2 id="report-detail-title">Reporte <span className="report-code mono">{selected.tracking_code}</span></h2>
            <StatusBadge status={selected.status}/>
            <p>Recibido <time dateTime={selected.created_at}>{received(selected.created_at)}</time></p>
          </header>
          <dl className="report-facts">
            <div><dt>Tipo</dt><dd>{categoryLabels[selected.category] || selected.category}</dd></div>
            <div><dt>Barrio</dt><dd>{selected.neighborhood || 'Barrio no informado'}</dd></div>
          </dl>
          <dl className="private-details">
            <div className="report-description"><dt>Descripción</dt><dd>{selected.description}</dd></div>
            <div><dt><Icon d={ICONS.lock} size={14}/>Ubicación exacta</dt><dd className="mono"><PinIcon className="inline-icon"/>{selected.latitude.toFixed(6)}, {selected.longitude.toFixed(6)}</dd></div>
            <div><dt>Referencia</dt><dd>{selected.address_reference || 'No informada'}</dd></div>
          </dl>
          <PrivateLocationMap report={selected}/>
          <form className="admin-update" onSubmit={save} aria-busy={saving}><fieldset className="report-edit-fields" disabled={saving}>
            <label>Estado<select value={changes.status} onChange={(event) => setChanges({ ...changes, status: event.target.value })}>{statuses.map((value) => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></label>
            <label>Mensaje público<textarea value={changes.public_status_message} onChange={(event) => setChanges({ ...changes, public_status_message: event.target.value })} maxLength="600"/></label>
            <label>Nota interna<textarea value={changes.internal_notes} onChange={(event) => setChanges({ ...changes, internal_notes: event.target.value })} maxLength="2000"/></label>
            <label>ID de posible duplicado<input value={changes.possible_duplicate_of} onChange={(event) => setChanges({ ...changes, possible_duplicate_of: event.target.value })} placeholder="UUID de otro reporte"/></label>
            <button className="primary-button" disabled={saving}>{saving ? 'Guardando…' : 'Guardar cambios'}</button>
          </fieldset></form>
          <dl className="report-facts report-retention"><div><dt>Retención hasta</dt><dd><time dateTime={selected.retention_until}>{new Date(selected.retention_until).toLocaleDateString('es-AR')}</time></dd></div></dl>
        </> : <div className="empty-admin"><ShieldIcon className="admin-shield"/><h2>Seleccioná un reporte</h2><p>La descripción y ubicación exactas sólo se cargan en este panel protegido.</p></div>}
      </section>
    </div>
  </main>)
}
