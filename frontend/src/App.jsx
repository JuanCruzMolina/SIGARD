import { useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Route, Routes, Link } from 'react-router-dom'
import { DATA_ERROR_MESSAGE, formatDate, loadSigardData } from './services/sigardData'
import Dashboard from './pages/Dashboard'
import Mapa from './pages/Mapa'
import Validacion from './pages/Validacion'
import Metodologia from './pages/Metodologia'
import './App.css'

function App() {
  const [data, setData] = useState(null)
  const [selectedCutoffDate, setSelectedCutoffDate] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    loadSigardData().then((loaded) => {
      setData(loaded)
      setSelectedCutoffDate(loaded.availableWeeks.default_cutoff_date)
    }).catch(() => setError(DATA_ERROR_MESSAGE))
  }, [])

  const shared = data ? { data, selectedCutoffDate, onCutoffChange: setSelectedCutoffDate } : {}
  return <BrowserRouter><div className="app-shell">
    <header className="site-header"><Link to="/" className="brand" aria-label="SIGARD, inicio"><span className="brand-mark">S</span><span><strong>SIGARD</strong><small>Sistema Inteligente de Gestión y Análisis de Riesgo de Dengue</small></span></Link><nav className="main-nav" aria-label="Navegación principal"><NavLink to="/" end>Resumen</NavLink><NavLink to="/mapa">Mapa territorial</NavLink><NavLink to="/validacion">Validación</NavLink><NavLink to="/metodologia">Metodología</NavLink></nav><span className="status-badge"><i /> Prototipo académico</span></header>
    <main>{error ? <div className="error-state" role="alert"><h2>{DATA_ERROR_MESSAGE}</h2></div> : !data || !selectedCutoffDate ? <div className="loading-state"><span className="spinner" />Cargando datos SIGARD…</div> : <Routes><Route path="/" element={<Dashboard {...shared} />} /><Route path="/mapa" element={<Mapa {...shared} />} /><Route path="/validacion" element={<Validacion data={data} />} /><Route path="/metodologia" element={<Metodologia data={data} />} /><Route path="*" element={<Dashboard {...shared} />} /></Routes>}</main>
    <footer className="site-footer">SIGARD · Departamento Capital, La Rioja <span>Corte seleccionado: {formatDate(selectedCutoffDate)}</span></footer>
  </div></BrowserRouter>
}
export default App
