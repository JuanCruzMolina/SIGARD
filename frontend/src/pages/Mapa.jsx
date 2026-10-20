import { useMemo, useState } from 'react'
import { getDisclaimer, getExperimentalCollection, getSelectedPrediction, getSelectedWeek } from '../services/sigardData'
import { MethodNotice, PageIntro, TemporalControls, TerritorialMap } from '../components/SigardComponents'
import ExperimentalSpatial from '../components/ExperimentalSpatial'
import { localResearchEnabled } from '../services/experimentalResults'

export default function Mapa({ data, selectedCutoffDate, onCutoffChange }) {
  const [territorialView, setTerritorialView] = useState('simulation')
  const [research, setResearch] = useState(false)
  const selectedWeek = getSelectedWeek(data, selectedCutoffDate)
  getSelectedPrediction(data, selectedCutoffDate)
  const simulation = useMemo(() => getExperimentalCollection(data, selectedCutoffDate), [data, selectedCutoffDate])
  const geojson = territorialView === 'context' ? data.territorialContext : simulation
  const disclaimer = territorialView === 'context' ? getDisclaimer(data.metadata, 'territorial_context') : `${getDisclaimer(data.metadata, 'experimental_spatial')} No representa casos observados ni una predicción espacial validada.`
  return <div className="content-wrap"><PageIntro title={research ? 'Análisis experimental A/B' : 'Mapa público agregado'}><p>{research ? 'Explorá scores por radio y semana y compará las evaluaciones retrospectivas de ambos modelos. Disponible sólo en la demostración local.' : 'Explorá el contexto territorial o la simulación espacial semanal sin exponer coordenadas individuales ni datos personales.'}</p></PageIntro>{localResearchEnabled() && <div className="segmented research-mode"><button type="button" aria-pressed={!research} onClick={() => setResearch(false)}>MVP sintético y contexto</button><button type="button" aria-pressed={research} onClick={() => setResearch(true)}>Investigación local A/B</button></div>}{research ? <ExperimentalSpatial geometry={data.territorialContext} /> : <><TemporalControls weeks={data.availableWeeks.weeks} selectedCutoffDate={selectedCutoffDate} onCutoffChange={onCutoffChange} selectedWeek={selectedWeek} territorialView={territorialView} onViewChange={setTerritorialView} /><MethodNotice title="Privacidad y alcance">{disclaimer}</MethodNotice><TerritorialMap geojson={geojson} view={territorialView} disclaimer={disclaimer} /></>}</div>
}
