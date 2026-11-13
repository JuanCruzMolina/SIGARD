import { useMemo, useState } from 'react'
import { getDisclaimer, getExperimentalCollection, getSelectedPrediction, getSelectedWeek } from '../services/sigardData'
import { MethodNotice, PageIntro, TemporalControls, TerritorialMap } from '../components/SigardComponents'
import HistoricalBacktest from '../components/HistoricalBacktest'
import { localResearchEnabled } from '../services/experimentalResults'

function PublicMap({ data, selectedCutoffDate, onCutoffChange }) {
  const [territorialView, setTerritorialView] = useState('simulation')
  const selectedWeek = getSelectedWeek(data, selectedCutoffDate)
  getSelectedPrediction(data, selectedCutoffDate)
  const simulation = useMemo(() => getExperimentalCollection(data, selectedCutoffDate), [data, selectedCutoffDate])
  const geojson = territorialView === 'context' ? data.territorialContext : simulation
  const disclaimer = territorialView === 'context' ? getDisclaimer(data.metadata, 'territorial_context') : `${getDisclaimer(data.metadata, 'experimental_spatial')} No representa casos observados ni una predicción espacial validada.`
  return <div className="content-wrap">
    <PageIntro title="Mapa público agregado"><p>Explorá el contexto territorial o la simulación espacial semanal sin exponer coordenadas individuales ni datos personales.</p></PageIntro>
    <TemporalControls weeks={data.availableWeeks.weeks} selectedCutoffDate={selectedCutoffDate} onCutoffChange={onCutoffChange} selectedWeek={selectedWeek} territorialView={territorialView} onViewChange={setTerritorialView} /><MethodNotice title="Privacidad y alcance">{disclaimer}</MethodNotice><TerritorialMap geojson={geojson} view={territorialView} disclaimer={disclaimer} />
  </div>
}

export default function Mapa(props) {
  return localResearchEnabled() ? <div className="content-wrap"><PageIntro title="Predicción semanal de dengue por radio censal"><p>Elegí una semana y mirá dónde y cuántos registros se esperaban, comparados con lo que ocurrió.</p><p className="pv-badge">Prototipo experimental — reconstrucción histórica, no uso operativo</p></PageIntro><HistoricalBacktest /></div> : <PublicMap {...props} />
}
