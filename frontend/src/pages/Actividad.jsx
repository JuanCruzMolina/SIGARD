import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageIntro } from '../components/SigardComponents'
import PublicActivity from '../components/PublicActivity'
import { loadActivity } from '../services/publicActivity.mjs'

// Real packages join the already approved public radio geometry; the fixture brings its own
// abstract cells so fictional values never land on real cartography.
async function loadGeometry(activity) {
  if (activity.geometry_source === 'inline') return activity.geometry
  const response = await fetch('/data/territorial_context.geojson')
  if (!response.ok) throw new Error('geometry')
  const collection = await response.json()
  return { type: 'FeatureCollection', features: collection.features.map(f => ({ type: 'Feature', geometry: f.geometry, properties: { radio_id: f.properties.radio_id } })) }
}

export default function Actividad() {
  const [state, setState] = useState({ status: 'loading' })
  useEffect(() => {
    let active = true
    loadActivity().then(async result => {
      if (!result.enabled) return active && setState({ status: 'disabled' })
      const geometry = await loadGeometry(result.activity)
      if (active) setState({ status: 'ready', activity: result.activity, geometry })
    }).catch(() => active && setState({ status: 'error' }))
    return () => { active = false }
  }, [])
  return <main><div className="content-wrap">
    <PageIntro title="Actividad registrada"><p>Niveles de registros de dengue por zona en bloques de cuatro semanas y la serie semanal de la ciudad. Datos agregados por zona; no muestran domicilios.</p></PageIntro>
    {state.status === 'loading' && <div className="loading-state" role="status"><span className="spinner" />Cargando actividad registrada…</div>}
    {state.status === 'disabled' && <div className="pa-disabled" role="status"><h2>La vista de actividad registrada no está habilitada</h2>
      <p>Su publicación requiere una autorización institucional que todavía no está disponible. Mientras tanto podés consultar el <Link to="/mapa">mapa público</Link>.</p></div>}
    {state.status === 'error' && <div className="error-state" role="alert"><h2>No fue posible cargar la cartografía de la vista.</h2></div>}
    {state.status === 'ready' && <PublicActivity activity={state.activity} geometry={state.geometry} />}
  </div></main>
}
