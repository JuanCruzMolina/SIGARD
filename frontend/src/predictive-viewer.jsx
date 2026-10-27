import { createRoot } from 'react-dom/client'
import PredictiveLocalViewer from './components/PredictiveLocalViewer'
import './predictive-viewer.css'

const root = createRoot(document.getElementById('root'))
if (window.location.protocol !== 'file:') {
  root.render(<main><h1>Demostración privada local</h1><p>Abrí el archivo HTML privado directamente desde tu equipo. Esta vista no se habilita en sitios web.</p></main>)
} else {
  try {
    const payload = JSON.parse(document.getElementById('sigard-private-payload').textContent)
    if (payload.schema !== 'sigard-private-predictive-viewer/1' || payload.geometry.features.length !== 256) throw new Error('Invalid local file')
    root.render(<PredictiveLocalViewer payload={payload} />)
  } catch {
    root.render(<main><h1>No fue posible abrir la demostración</h1><p>Regenerá el archivo con la consulta local. No se muestran estimaciones incompletas.</p></main>)
  }
}
