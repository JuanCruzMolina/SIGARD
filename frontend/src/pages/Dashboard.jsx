import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { formatDate, formatDateRange, formatNumber, getDisclaimer, getExperimentalCollection, getSelectedPrediction, getSelectedWeek } from '../services/sigardData'
import { MethodNotice, PageIntro, StatCard, TemporalControls, TerritorialMap, TopRadios } from '../components/SigardComponents'

export default function Dashboard({ data, selectedCutoffDate, onCutoffChange }) {
  const [territorialView, setTerritorialView] = useState('simulation')
  const selectedWeek = getSelectedWeek(data, selectedCutoffDate)
  const prediction = getSelectedPrediction(data, selectedCutoffDate)
  const simulation = useMemo(() => getExperimentalCollection(data, selectedCutoffDate), [data, selectedCutoffDate])
  const geojson = territorialView === 'context' ? data.territorialContext : simulation
  const disclaimer = territorialView === 'context' ? getDisclaimer(data.metadata, 'territorial_context') : `${getDisclaimer(data.metadata, 'experimental_spatial')} No representa casos observados ni una predicción espacial validada.`
  const title = territorialView === 'context' ? 'Contexto territorial relativo' : 'Simulación espacial experimental'
  return <div className="content-wrap public-home">
    <PageIntro title="Situación territorial del dengue en La Rioja Capital"><p>Consultá la información pública disponible por semana. Las ubicaciones se presentan de forma agregada para proteger la identidad y el domicilio de las personas.</p></PageIntro>
    <section className="map-stage" aria-labelledby="public-map-title">
      <div className="map-stage-header">
        <div><span className="privacy-seal">Privacidad aplicada</span><h2 id="public-map-title">{title}</h2><p>Semana objetivo: {formatDateRange(selectedWeek.target_week_start, selectedWeek.target_week_end)}</p></div>
        <Link className="text-link" to="/mapa">Explorar en detalle <span aria-hidden="true">→</span></Link>
      </div>
      <TemporalControls weeks={data.availableWeeks.weeks} selectedCutoffDate={selectedCutoffDate} onCutoffChange={onCutoffChange} selectedWeek={selectedWeek} territorialView={territorialView} onViewChange={setTerritorialView} />
      <TerritorialMap geojson={geojson} view={territorialView} disclaimer={disclaimer} compact />
      <MethodNotice title={territorialView === 'simulation' ? 'Capa experimental, no evidencia epidemiológica' : 'Lectura correcta del mapa'}>{disclaimer}</MethodNotice>
    </section>
    <section className="situation-ledger" aria-label="Resumen de la semana seleccionada">
      <StatCard label="Semana epidemiológica objetivo" value={formatDateRange(selectedWeek.target_week_start, selectedWeek.target_week_end)} detail="Período futuro estimado" />
      <StatCard label="Estimación departamental" value={`${formatNumber(prediction.predicted_cases_rounded, 0)} casos`} detail={`Predicción temporal · valor continuo ${formatNumber(prediction.predicted_cases, 2)}`} />
      <StatCard label="Cobertura territorial" value={`${data.territorialContext.features.length} radios`} detail="Departamento Capital" />
      <StatCard label="Datos disponibles hasta" value={formatDate(selectedCutoffDate)} detail={data.temporalPredictions.model.variant} />
    </section>
    <section className="provenance-strip" aria-labelledby="provenance-title"><div><h2 id="provenance-title">Qué estás viendo</h2><p>Cada resultado conserva su procedencia para evitar interpretaciones incorrectas.</p></div><ul><li><i className="source-dot observed" />Observaciones agregadas</li><li><i className="source-dot predicted" />Predicción temporal</li><li><i className="source-dot synthetic" />Simulación espacial</li></ul><Link className="text-link" to="/metodologia">Consultar metodología <span aria-hidden="true">→</span></Link></section>
    <section className="panel ranking-panel"><div className="section-heading"><div><h2>{territorialView === 'context' ? 'Radios con mayor contexto territorial relativo' : 'Mayor señal dentro de la simulación'}</h2><p>Orden relativo de la capa seleccionada; no constituye un ranking sanitario oficial.</p></div></div><TopRadios geojson={geojson} view={territorialView} /></section>
  </div>
}
