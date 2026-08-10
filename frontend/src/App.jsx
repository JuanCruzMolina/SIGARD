import { useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Route, Routes, Link } from 'react-router-dom'
import { loadSigardData, formatDate } from './services/sigardData'
import Dashboard from './pages/Dashboard'
import Mapa from './pages/Mapa'
import Validacion from './pages/Validacion'
import Metodologia from './pages/Metodologia'
import './App.css'

function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadSigardData().then(setData).catch((err) => setError(err.message))
  }, [])

  return (
    <BrowserRouter>
      <div className="app-shell">
        <header className="site-header">
          <Link to="/" className="brand" aria-label="SIGARD, inicio">
            <span className="brand-mark">S</span>
            <span><strong>SIGARD</strong><small>Sistema Inteligente de Gestión y Análisis de Riesgo de Dengue</small></span>
          </Link>
          <nav className="main-nav" aria-label="Navegación principal">
            <NavLink to="/" end>Resumen</NavLink>
            <NavLink to="/mapa">Mapa de riesgo</NavLink>
            <NavLink to="/validacion">Validación</NavLink>
            <NavLink to="/metodologia">Metodología</NavLink>
          </nav>
          <span className="status-badge"><i /> Prototipo académico</span>
        </header>
        <main>
          {error ? <div className="error-state" role="alert"><h2>No se pudo cargar la información</h2><p>{error}</p></div> : !data ? <div className="loading-state"><span className="spinner" />Cargando datos SIGARD…</div> : <Routes>
            <Route path="/" element={<Dashboard data={data} />} />
            <Route path="/mapa" element={<Mapa data={data} />} />
            <Route path="/validacion" element={<Validacion data={data} />} />
            <Route path="/metodologia" element={<Metodologia data={data} />} />
            <Route path="*" element={<Dashboard data={data} />} />
          </Routes>}
        </main>
        <footer className="site-footer">SIGARD · La Rioja Capital · apoyo a la vigilancia territorial del dengue {data?.summary?.cutoff_date && <span>Datos del corte: {formatDate(data.summary.cutoff_date)}</span>}</footer>
      </div>
    </BrowserRouter>
  )
}

export default App

