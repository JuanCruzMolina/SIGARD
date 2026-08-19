import { useCallback, useEffect, useState } from 'react'
import L from 'leaflet'
import { GeoJSON, MapContainer, Marker } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { AlertIcon, PinIcon, ShieldIcon } from '../components/InfoIcons'
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
  return <div className="private-map"><MapContainer key={report.id} center={[report.latitude, report.longitude]} zoom={14} scrollWheelZoom={false}>{territorialContext && <GeoJSON data={territorialContext} style={{ color: '#88a9a2', weight: 1, fillColor: '#e9f0ec', fillOpacity: .55 }}/>}<Marker position={[report.latitude, report.longitude]} icon={privateIcon}/></MapContainer><small>Contexto censal local de SIGARD, sin teselas ni servicios cartográficos externos.</small></div>
}

export default function AdminReports() {
  const [token, setToken] = useState(() => sessionStorage.getItem('sigard_admin_token') || '')
  const [credentials, setCredentials] = useState({ email: '', password: '' })
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ category: '', status: '', neighborhood: '', date_from: '', date_to: '' })
  const [listing, setListing] = useState({ items: [], total: 0, page: 1, page_size: 25 })
  const [selected, setSelected] = useState(null)
  const [changes, setChanges] = useState({ status: '', public_status_message: '', internal_notes: '', possible_duplicate_of: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const logout = useCallback(() => { sessionStorage.removeItem('sigard_admin_token'); setToken(''); setSelected(null) }, [])
  const loadList = useCallback(async () => {
    if (!token) return
    setLoading(true); setError('')
    try { setListing(await listAdminReports(token, { ...filters, page: String(page) })) }
    catch (requestError) { setError(requestError.message); if (requestError.status === 401) logout() }
    finally { setLoading(false) }
  }, [filters, logout, page, token])

  useEffect(() => {
    if (!token) return undefined
    let active = true
    listAdminReports(token, { ...filters, page: String(page) })
      .then((result) => { if (active) setListing(result) })
      .catch((requestError) => {
        if (!active) return
        setError(requestError.message)
        if (requestError.status === 401) logout()
      })
    return () => { active = false }
  }, [filters, logout, page, token])

  async function login(event) {
    event.preventDefault(); setLoading(true); setError('')
    try { const result = await adminLogin(credentials); sessionStorage.setItem('sigard_admin_token', result.access_token); setToken(result.access_token) }
    catch (requestError) { setError(requestError.message) }
    finally { setLoading(false) }
  }

  async function selectReport(id) {
    setError('')
    try {
      const report = await getAdminReport(token, id)
      setSelected(report)
      setChanges({ status: report.status, public_status_message: report.public_status_message || '', internal_notes: report.internal_notes || '', possible_duplicate_of: report.possible_duplicate_of || '' })
    } catch (requestError) { setError(requestError.message) }
  }

  async function save(event) {
    event.preventDefault(); setLoading(true); setError('')
    try {
      const updated = await updateAdminReport(token, selected.id, changes)
      setSelected(updated); await loadList()
    } catch (requestError) { setError(requestError.message) }
    finally { setLoading(false) }
  }

  if (!token) return <main className="admin-login-page"><form className="admin-login" onSubmit={login}><ShieldIcon className="admin-shield"/><h1>Bandeja de reportes</h1><p>Acceso restringido a personal autorizado. Las ubicaciones y descripciones son privadas.</p><label>Correo institucional<input type="email" value={credentials.email} onChange={(event) => setCredentials({ ...credentials, email: event.target.value })} required/></label><label>Contraseña<input type="password" value={credentials.password} onChange={(event) => setCredentials({ ...credentials, password: event.target.value })} required minLength="8"/></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary-button" disabled={loading}>{loading ? 'Ingresando…' : 'Ingresar'}</button></form></main>

  return <main className="admin-page"><header className="admin-header"><div><h1>Reportes ciudadanos</h1><p>Operación interna. Estos registros no son casos de dengue ni evidencia epidemiológica.</p></div><div><button className="secondary-button" type="button" onClick={() => downloadAdminExport(token).catch((requestError) => setError(requestError.message))}>Exportar CSV</button><button className="text-button" type="button" onClick={logout}>Cerrar sesión</button></div></header><div className="sensitive-banner"><AlertIcon className="info-icon"/><p><strong>Información privada.</strong> No copies coordenadas exactas a mapas públicos ni herramientas analíticas de terceros.</p></div><section className="admin-filters" aria-label="Filtros"><label>Categoría<select value={filters.category} onChange={(event) => { setPage(1); setFilters({ ...filters, category: event.target.value }) }}><option value="">Todas</option>{Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Estado<select value={filters.status} onChange={(event) => { setPage(1); setFilters({ ...filters, status: event.target.value }) }}><option value="">Todos</option>{statuses.map((value) => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></label><label>Barrio<input value={filters.neighborhood} onChange={(event) => { setPage(1); setFilters({ ...filters, neighborhood: event.target.value }) }} placeholder="Buscar barrio"/></label><label>Desde<input type="date" value={filters.date_from} onChange={(event) => { setPage(1); setFilters({ ...filters, date_from: event.target.value }) }}/></label><label>Hasta<input type="date" value={filters.date_to} onChange={(event) => { setPage(1); setFilters({ ...filters, date_to: event.target.value }) }}/></label></section>{error && <p className="form-error admin-error" role="alert">{error}</p>}<div className="admin-workspace"><section className="report-inbox" aria-label="Listado de reportes"><header><strong>{listing.total} reportes</strong>{loading && <span>Cargando…</span>}</header><div>{listing.items.map((report) => <button type="button" key={report.id} className={selected?.id === report.id ? 'selected' : ''} onClick={() => selectReport(report.id)}><span className={`status-chip ${report.status}`}>{statusLabels[report.status]}</span><strong>{report.tracking_code}</strong><small>{categoryLabels[report.category] || report.category}</small><time>{new Date(report.created_at).toLocaleString('es-AR')}</time></button>)}</div><footer><button type="button" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</button><span>Página {page}</span><button type="button" disabled={page * listing.page_size >= listing.total} onClick={() => setPage((value) => value + 1)}>Siguiente</button></footer></section><section className="report-detail">{selected ? <><header><span className={`status-chip ${selected.status}`}>{statusLabels[selected.status]}</span><h2>{selected.tracking_code}</h2><p>{categoryLabels[selected.category] || selected.category} · {selected.neighborhood || 'Barrio no informado'}</p></header><PrivateLocationMap report={selected}/><dl className="private-details"><div><dt>Ubicación exacta</dt><dd><PinIcon className="inline-icon"/>{selected.latitude.toFixed(6)}, {selected.longitude.toFixed(6)}</dd></div><div><dt>Referencia</dt><dd>{selected.address_reference || 'No informada'}</dd></div><div><dt>Descripción</dt><dd>{selected.description}</dd></div><div><dt>Retención hasta</dt><dd>{new Date(selected.retention_until).toLocaleDateString('es-AR')}</dd></div></dl><form className="admin-update" onSubmit={save}><label>Estado<select value={changes.status} onChange={(event) => setChanges({ ...changes, status: event.target.value })}>{statuses.map((value) => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></label><label>Mensaje público<textarea value={changes.public_status_message} onChange={(event) => setChanges({ ...changes, public_status_message: event.target.value })} maxLength="600"/></label><label>Nota interna<textarea value={changes.internal_notes} onChange={(event) => setChanges({ ...changes, internal_notes: event.target.value })} maxLength="2000"/></label><label>ID de posible duplicado<input value={changes.possible_duplicate_of} onChange={(event) => setChanges({ ...changes, possible_duplicate_of: event.target.value })} placeholder="UUID de otro reporte"/></label><button className="primary-button" disabled={loading}>Guardar cambios</button></form></> : <div className="empty-admin"><ShieldIcon className="admin-shield"/><h2>Seleccioná un reporte</h2><p>La descripción y ubicación exactas sólo se cargan en este panel protegido.</p></div>}</section></div></main>
}
