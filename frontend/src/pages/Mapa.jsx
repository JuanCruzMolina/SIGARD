import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDisclaimer, getExperimentalCollection, getSelectedPrediction, getSelectedWeek } from '../services/sigardData'
import { MethodNotice, PageIntro, TemporalControls, TerritorialMap } from '../components/SigardComponents'

// F3: /mapa is always the public map. In local development the predictive viewer moved to
// Administración; `predictiveLink` (given only there) points to it, keeping any viewer state.
export default function Mapa({ data, selectedCutoffDate, onCutoffChange, predictiveLink }) {
  const [territorialView, setTerritorialView] = useState('simulation')
  const selectedWeek = getSelectedWeek(data, selectedCutoffDate)
  getSelectedPrediction(data, selectedCutoffDate)
  const simulation = useMemo(() => getExperimentalCollection(data, selectedCutoffDate), [data, selectedCutoffDate])
  const geojson = territorialView === 'context' ? data.territorialContext : simulation
  const disclaimer = territorialView === 'context' ? getDisclaimer(data.metadata, 'territorial_context') : `${getDisclaimer(data.metadata, 'experimental_spatial')} No representa casos observados ni una predicción espacial validada.`
  return <div className="content-wrap">
    {predictiveLink && <p className="predictive-moved" role="note"><Link to={predictiveLink}>El módulo predictivo está en Administración</Link></p>}
    <PageIntro title="Mapa público agregado"><p>Explorá el contexto territorial o la simulación espacial semanal sin exponer coordenadas individuales ni datos personales.</p></PageIntro>
    <TemporalControls weeks={data.availableWeeks.weeks} selectedCutoffDate={selectedCutoffDate} onCutoffChange={onCutoffChange} selectedWeek={selectedWeek} territorialView={territorialView} onViewChange={setTerritorialView} /><MethodNotice title="Privacidad y alcance">{disclaimer}</MethodNotice><TerritorialMap geojson={geojson} view={territorialView} disclaimer={disclaimer} />
  </div>
}
