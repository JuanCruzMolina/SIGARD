import { useCallback, useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { GeoJSON, MapContainer, Marker } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { AlertIcon, PinIcon, ShieldIcon } from '../components/InfoIcons'
import AdminAccounts from '../components/AdminAccounts'
import {
  adminLogin,
  downloadAdminExport,
  getAdminReport,
  listAdminReports,
  updateAdminReport,
} from '../services/citizenReports'
import '../Prevention.css'

const statuses = ['recibido', 'en_revision', 'pendiente_de_derivacion', 'derivado', 'resuelto', 'descartado']
const statusLabels = { recibido: 'Recibido', en_revision: 'En revisión', pendiente_de_derivacion: 'Pendiente de derivación', derivado: 'Derivado', resuelto: 'Resuelto', descartado: 'Descartado' }
const categoryLabels = { agua_acumulada: 'Agua acumulada', neumaticos_chatarra: 'Neumáticos o chatarra', microbasural: 'Microbasural', criadero_espacio_publico: 'Criadero en espacio público', alta_presencia_mosquitos: 'Alta presencia de mosquitos', evaluacion_control_vectorial: 'Evaluación de control vectorial', otro: 'Otro' }
const privateIcon = L.divIcon({ className: '', html: '<span class="report-marker private"></span>', iconSize: [32, 38], iconAnchor: [16, 34] })
const emptyFilters = { category: '', status: '', neighborhood: '', date_from: '', date_to: '' }
const emptyListing = { items: [], total: 0, page: 1, page_size: 25 }

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

export default function AdminReports() {
  const [token, setToken] = useState(() => sessionStorage.getItem('sigard_admin_token') || '')
  const [credentials, setCredentials] = useState({ email: '', password: '' })
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState(emptyFilters)
  const [readyFilters, setReadyFilters] = useState(emptyFilters)
  const [listResult, setListResult] = useState({ key: '', data: emptyListing, error: '' })
  const [refresh, setRefresh] = useState(0)
  const [selected, setSelected] = useState(null)
  const [changes, setChanges] = useState({ status: '', public_status_message: '', internal_notes: '', possible_duplicate_of: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [panel, setPanel] = useState('reports')
  const [sessionNotice, setSessionNotice] = useState('')
  const [detailLoading, setDetailLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)
  const requests = useRef({})
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

  const logout = useCallback(() => { cancelRequests(); sessionStorage.removeItem('sigard_admin_token'); setToken(''); setSelected(null); setListResult({ key: '', data: emptyListing, error: '' }); setPage(1); setFilters(emptyFilters); setSaving(false); setExporting(false); setDetailLoading(false); setLoading(false); setChanges({ status: '', public_status_message: '', internal_notes: '', possible_duplicate_of: '' }); setCredentials({ email: '', password: '' }); setPanel('reports'); setSessionNotice(''); setError('') }, [cancelRequests])
  const sessionExpired = useCallback((message) => { logout(); setError(''); setSessionNotice(message) }, [logout])
  const handleRequestError = useCallback((requestError) => {
    if (requestError.status === 401 || requestError.status === 403) sessionExpired('La sesión venció, fue revocada o ya no tiene permisos. Ingresá nuevamente.')
    else setError(requestError.message)
  }, [sessionExpired])
  const loadList = () => setRefresh(value => value + 1)

  useEffect(() => {
    if (!token || panel !== 'reports' || invalidDates || filters !== readyFilters) return undefined
    const request = beginRequest('list')
    listAdminReports(token, { ...filters, page: String(page) }, { signal: request.signal })
      .then((data) => { if (!request.signal.aborted) setListResult({ key: requestKey, data, error: '' }) })
      .catch((requestError) => {
        if (request.signal.aborted) return
        if (requestError.status === 401 || requestError.status === 403) handleRequestError(requestError)
        else setListResult({ key: requestKey, data: emptyListing, error: requestError.message })
      })
    return () => request.abort()
  }, [beginRequest, filters, handleRequestError, invalidDates, page, panel, readyFilters, requestKey, token])

  function changeFilters(next) {
    requests.current.detail?.abort(); requests.current.export?.abort()
    setSelected(null); setDetailLoading(false); setExporting(false); setError(''); setPage(1); setFilters(next)
  }

  async function login(event) {
    const request = beginRequest('login')
    event.preventDefault(); setLoading(true); setError(''); setSessionNotice('')
    try {
      const result = await adminLogin(credentials, { signal: request.signal })
      if (!request.signal.aborted) { sessionStorage.setItem('sigard_admin_token', result.access_token); setToken(result.access_token) }
    } catch (requestError) { if (!request.signal.aborted) setError(requestError.message) }
    finally { if (!request.signal.aborted) { setLoading(false); setCredentials({ email: '', password: '' }) } }
  }

  async function selectReport(id) {
    const request = beginRequest('detail')
    setError(''); setSelected(null); setDetailLoading(true)
    try {
      const report = await getAdminReport(token, id, { signal: request.signal })
      if (request.signal.aborted) return
      setSelected(report)
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
      if (!request.signal.aborted) { setSelected(updated); loadList() }
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

  if (!token) return <main className="admin-login-page"><form className="admin-login" onSubmit={login}><ShieldIcon className="admin-shield"/><h1>Bandeja de reportes</h1><p>Acceso restringido a personal autorizado. Las ubicaciones y descripciones son privadas.</p>{sessionNotice && <p role="status">{sessionNotice}</p>}<label>Correo institucional<input type="email" value={credentials.email} onChange={(event) => setCredentials({ ...credentials, email: event.target.value })} required maxLength="150" autoComplete="username"/></label><label>Contraseña<input type="password" value={credentials.password} onChange={(event) => setCredentials({ ...credentials, password: event.target.value })} required minLength="8" maxLength="200" autoComplete="current-password"/></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary-button" disabled={loading}>{loading ? 'Ingresando…' : 'Ingresar'}</button></form></main>

  if (panel === 'accounts') return <AdminAccounts token={token} onBack={() => { loadList(); setPanel('reports') }} onLogout={logout} onSessionExpired={sessionExpired}/>

  return <main className="admin-page"><header className="admin-header"><div><h1>Reportes ciudadanos</h1><p>Operación interna. Estos registros no son casos de dengue ni evidencia epidemiológica.</p></div><div><button className="secondary-button" type="button" disabled={saving} onClick={() => { cancelRequests(); setSelected(null); setDetailLoading(false); setExporting(false); setPanel('accounts') }}>Gestionar cuentas</button><button className="secondary-button" type="button" disabled={exporting || listLoading || saving || Boolean(listError)} onClick={exportResults}>{exporting ? 'Exportando…' : 'Exportar CSV'}</button><button className="text-button" type="button" onClick={logout}>Cerrar sesión</button></div></header><div className="sensitive-banner"><AlertIcon className="info-icon"/><p><strong>Información privada.</strong> No copies coordenadas exactas a mapas públicos ni herramientas analíticas de terceros.</p></div><fieldset className="admin-filters" disabled={saving} aria-label="Filtros"><label>Categoría<select value={filters.category} onChange={(event) => { changeFilters({ ...filters, category: event.target.value }) }}><option value="">Todas</option>{Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Estado<select value={filters.status} onChange={(event) => { changeFilters({ ...filters, status: event.target.value }) }}><option value="">Todos</option>{statuses.map((value) => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></label><label>Barrio<input value={filters.neighborhood} onChange={(event) => { changeFilters({ ...filters, neighborhood: event.target.value }) }} placeholder="Buscar barrio"/></label><label>Desde<input type="date" value={filters.date_from} onChange={(event) => { changeFilters({ ...filters, date_from: event.target.value }) }}/></label><label>Hasta<input type="date" value={filters.date_to} onChange={(event) => { changeFilters({ ...filters, date_to: event.target.value }) }}/></label><button className="text-button" type="button" onClick={() => changeFilters(emptyFilters)}>Limpiar filtros</button></fieldset>{listError && <div className="form-error admin-error" role="alert"><p>{listError}</p>{!invalidDates && <button type="button" className="secondary-button" onClick={loadList}>Reintentar listado</button>}</div>}{error && <p className="form-error admin-error" role="alert">{error}</p>}<div className="admin-workspace"><section className="report-inbox" aria-label="Listado de reportes" aria-busy={listLoading}><header><strong>{listing.total} reportes</strong>{listLoading && <span role="status">Cargando reportes…</span>}</header><div>{!listLoading && !listError && !listing.items.length && <p className="inbox-empty" role="status">No hay reportes para estos filtros.</p>}{listing.items.map((report) => <button type="button" key={report.id} disabled={saving} aria-pressed={selected?.id === report.id} className={selected?.id === report.id ? 'selected' : ''} onClick={() => selectReport(report.id)}><span className={`status-chip ${report.status}`}>{statusLabels[report.status]}</span><strong>{report.tracking_code}</strong><small>{categoryLabels[report.category] || report.category}</small><time>{new Date(report.created_at).toLocaleString('es-AR')}</time></button>)}</div><footer><button type="button" disabled={listLoading || saving || page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</button><span>Página {page}</span><button type="button" disabled={listLoading || saving || page * listing.page_size >= listing.total} onClick={() => setPage((value) => value + 1)}>Siguiente</button></footer></section><section className="report-detail" aria-busy={detailLoading || saving}>{detailLoading ? <p role="status">Cargando detalle del reporte…</p> : selected ? <><header><span className={`status-chip ${selected.status}`}>{statusLabels[selected.status]}</span><h2>{selected.tracking_code}</h2><p>{categoryLabels[selected.category] || selected.category} · {selected.neighborhood || 'Barrio no informado'}</p></header><PrivateLocationMap report={selected}/><dl className="private-details"><div><dt>Ubicación exacta</dt><dd><PinIcon className="inline-icon"/>{selected.latitude.toFixed(6)}, {selected.longitude.toFixed(6)}</dd></div><div><dt>Referencia</dt><dd>{selected.address_reference || 'No informada'}</dd></div><div><dt>Descripción</dt><dd>{selected.description}</dd></div><div><dt>Retención hasta</dt><dd>{new Date(selected.retention_until).toLocaleDateString('es-AR')}</dd></div></dl><form className="admin-update" onSubmit={save} aria-busy={saving}><fieldset className="report-edit-fields" disabled={saving}><label>Estado<select value={changes.status} onChange={(event) => setChanges({ ...changes, status: event.target.value })}>{statuses.map((value) => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></label><label>Mensaje público<textarea value={changes.public_status_message} onChange={(event) => setChanges({ ...changes, public_status_message: event.target.value })} maxLength="600"/></label><label>Nota interna<textarea value={changes.internal_notes} onChange={(event) => setChanges({ ...changes, internal_notes: event.target.value })} maxLength="2000"/></label><label>ID de posible duplicado<input value={changes.possible_duplicate_of} onChange={(event) => setChanges({ ...changes, possible_duplicate_of: event.target.value })} placeholder="UUID de otro reporte"/></label><button className="primary-button" disabled={saving}>{saving ? 'Guardando…' : 'Guardar cambios'}</button></fieldset></form></> : <div className="empty-admin"><ShieldIcon className="admin-shield"/><h2>Seleccioná un reporte</h2><p>La descripción y ubicación exactas sólo se cargan en este panel protegido.</p></div>}</section></div></main>
}
