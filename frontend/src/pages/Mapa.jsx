import { useMemo, useState } from 'react'
import { getDisclaimer, getExperimentalCollection, getSelectedPrediction, getSelectedWeek } from '../services/sigardData'
import { MethodNotice, PageIntro, TemporalControls, TerritorialMap } from '../components/SigardComponents'

export default function Mapa({ data, selectedCutoffDate, onCutoffChange }) {
  const [territorialView, setTerritorialView] = useState('context')
  const selectedWeek = getSelectedWeek(data, selectedCutoffDate)
  getSelectedPrediction(data, selectedCutoffDate)
  const simulation = useMemo(() => getExperimentalCollection(data, selectedCutoffDate), [data, selectedCutoffDate])
  const geojson = territorialView === 'context' ? data.territorialContext : simulation
  const disclaimer = territorialView === 'context' ? getDisclaimer(data.metadata, 'territorial_context') : `${getDisclaimer(data.metadata, 'experimental_spatial')} No representa casos observados ni una predicción espacial validada.`
  return <div className="content-wrap"><PageIntro eyebrow="Exploración territorial" title="Mapa territorial"><p>Consultá el contexto territorial estable o la simulación espacial correspondiente a una semana disponible.</p></PageIntro><TemporalControls weeks={data.availableWeeks.weeks} selectedCutoffDate={selectedCutoffDate} onCutoffChange={onCutoffChange} selectedWeek={selectedWeek} territorialView={territorialView} onViewChange={setTerritorialView} /><MethodNotice>{disclaimer}</MethodNotice><TerritorialMap geojson={geojson} view={territorialView} disclaimer={disclaimer} /></div>
}
