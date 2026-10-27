import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes, Link, useLocation } from 'react-router-dom'
import { DATA_ERROR_MESSAGE, formatDate, loadSigardData } from './services/sigardData'
import { localResearchEnabled } from './services/experimentalResults'
import { demoMode } from './services/demoMode'
import Dashboard from './pages/Dashboard'
import Mapa from './pages/Mapa'
import Validacion from './pages/Validacion'
import Metodologia from './pages/Metodologia'
import Prevencion from './pages/Prevencion'
import AdminReports from './pages/AdminReports'
import './App.css'

function EpidemiologicalRoute({ data, error, selectedCutoffDate, children }) {
  if (error) return <main><div className="error-state" role="alert"><h2>{DATA_ERROR_MESSAGE}</h2></div></main>
  if (!data || !selectedCutoffDate) return <main><div className="loading-state"><span className="spinner" />Cargando datos SIGARD…</div></main>
  return <main>{children}</main>
}

function AppContent() {
  const [data, setData] = useState(null)
  const [selectedCutoffDate, setSelectedCutoffDate] = useState('')
  const [error, setError] = useState(null)
  const { pathname } = useLocation()
  const localResearch = localResearchEnabled()
  const needsEpidemiologicalData = !pathname.startsWith('/prevencion') && !pathname.startsWith('/admin/')

  useEffect(() => {
    if (!needsEpidemiologicalData || data || error) return
    loadSigardData().then((loaded) => {
      setData(loaded)
      setSelectedCutoffDate(loaded.availableWeeks.default_cutoff_date)
    }).catch(() => setError(DATA_ERROR_MESSAGE))
  }, [data, error, needsEpidemiologicalData])

  const shared = data ? { data, selectedCutoffDate, onCutoffChange: setSelectedCutoffDate } : null
  return <div className="app-shell">
    <div className="privacy-bar"><span>{pathname.startsWith('/admin/') ? 'Área administrativa' : localResearch ? 'Demostración local' : 'Vista pública'}</span><p>Los datos epidemiológicos son agregados y las ubicaciones de reportes ciudadanos permanecen privadas.</p></div>
    {demoMode && <aside className="demo-notice" aria-label="Demostración ficticia y temporal"><strong>Demo integral · entorno ficticio y temporal</strong><p>Reportes, consulta por radio, ingestión y alertas usan ejemplos inventados. Se eliminan al cerrar. Los resultados privados A/B y V1/V2/V3 no se cargan aquí. Prevención y cartografía pública conservan su procedencia; mapas sin fondo externo.</p><Link to="/prevencion#reportar">Crear reporte ficticio</Link>{' · '}<Link to="/prevencion#seguimiento">Seguimiento</Link>{' · '}<Link to="/admin/reportes">Administración demo</Link></aside>}
    <header className="site-header"><Link to="/" className="brand" aria-label="SIGARD, inicio"><span className="brand-mark" aria-hidden="true">S</span><span><strong>SIGARD</strong><small>Vigilancia territorial del dengue</small></span></Link><nav className="main-nav" aria-label="Navegación principal"><NavLink to={localResearch ? '/dashboard' : '/'} end>Situación actual</NavLink><NavLink to="/mapa">{localResearch ? 'Panel A/B y MVP' : 'Mapa público'}</NavLink><NavLink to="/prevencion">Prevención y ayuda</NavLink><NavLink to="/validacion">Validación</NavLink><NavLink to="/metodologia">Cómo funciona</NavLink><NavLink to="/admin/reportes">Administración</NavLink></nav><span className="status-badge">Prototipo académico</span></header>
    <Routes>
      <Route path="/prevencion" element={<Prevencion />} />
      <Route path="/admin/reportes" element={<AdminReports />} />
      <Route path="/" element={localResearch ? <Navigate to="/mapa" replace /> : <EpidemiologicalRoute data={data} error={error} selectedCutoffDate={selectedCutoffDate}>{shared && <Dashboard {...shared} />}</EpidemiologicalRoute>} />
      {localResearch && <Route path="/dashboard" element={<EpidemiologicalRoute data={data} error={error} selectedCutoffDate={selectedCutoffDate}>{shared && <Dashboard {...shared} />}</EpidemiologicalRoute>} />}
      <Route path="/mapa" element={<EpidemiologicalRoute data={data} error={error} selectedCutoffDate={selectedCutoffDate}>{shared && <Mapa {...shared} />}</EpidemiologicalRoute>} />
      <Route path="/validacion" element={<EpidemiologicalRoute data={data} error={error} selectedCutoffDate={selectedCutoffDate}>{data && <Validacion data={data} />}</EpidemiologicalRoute>} />
      <Route path="/metodologia" element={<EpidemiologicalRoute data={data} error={error} selectedCutoffDate={selectedCutoffDate}>{data && <Metodologia data={data} />}</EpidemiologicalRoute>} />
      <Route path="*" element={<Prevencion />} />
    </Routes>
    <footer className="site-footer"><span><strong>SIGARD</strong> · La Rioja Capital</span>{selectedCutoffDate && <span>Último corte epidemiológico disponible: {formatDate(selectedCutoffDate)}</span>}{data && <span>Fuente técnica: {data.dataSource === 'api' ? `API ${data.availableWeeks.publication?.version || 'versionada'}` : 'respaldo estático local'}</span>}<span>Información orientativa · No reemplaza indicaciones sanitarias oficiales</span></footer>
  </div>
}

function App() {
  return <BrowserRouter><AppContent /></BrowserRouter>
}
export default App
