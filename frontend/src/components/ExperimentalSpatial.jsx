import { useEffect, useMemo, useState } from 'react'
import { TerritorialMap, MethodNotice } from './SigardComponents'
import { experimentalWarning, joinExperimentalGeometry, validateComparison } from '../services/experimentalContract.mjs'
import { researchCatalog, researchRequest, researchScores } from '../services/experimentalResults'
import { formatNumber } from '../services/sigardData'
import { partitionNames } from '../services/experimentalAnalysis.mjs'
import ExperimentalAnalysis from './ExperimentalAnalysis'

export default function ExperimentalSpatial({ geometry }) {
  const [catalog, setCatalog] = useState(null)
  const [modelId, setModelId] = useState('A')
  const [week, setWeek] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loadingCatalog, setLoadingCatalog] = useState(true)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [radio, setRadio] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [comparisonError, setComparisonError] = useState('')
  const model = catalog?.models.find(m => m.model_id === modelId)
  const requestKey = `${modelId}/${week}`
  const current = result?.key === requestKey ? result.value : null
  const mapGeometry = useMemo(() => current ? joinExperimentalGeometry(geometry, current) : null, [geometry, current])
  const currentComparison = comparison?.key === `${requestKey}/${radio}` ? comparison.value : null

  useEffect(() => {
    const controller = new AbortController()
    researchCatalog(controller.signal)
      .then(c => {
        if (controller.signal.aborted) return
        setCatalog(c); setModelId(c.models[0].model_id); setWeek(c.models[0].weeks[0].target_week_start)
        setError('')
      })
      .catch(e => { if (!controller.signal.aborted) setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setLoadingCatalog(false) })
    return () => controller.abort()
  }, [loadAttempt])

  useEffect(() => {
    if (!model || !week) return
    const controller = new AbortController()
    researchScores(model, week, geometry.features.map(f => f.properties.radio_id), controller.signal)
      .then(value => { if (!controller.signal.aborted) { setResult({ key: requestKey, value }); setError('') } })
      .catch(e => { if (!controller.signal.aborted) {
        setResult(null); setError(e.message)
      } })
    return () => controller.abort()
  }, [model, week, geometry, requestKey])

  useEffect(() => {
    if (!radio || !current) return
    const controller = new AbortController()
    researchRequest(`/comparison/${encodeURIComponent(week)}/${encodeURIComponent(radio)}`, controller.signal)
      .then(value => {
        if (controller.signal.aborted) return
        validateComparison(value, catalog, radio, week)
        setComparison({ key: `${requestKey}/${radio}`, value }); setComparisonError('')
      })
      .catch(e => { if (!controller.signal.aborted) {
        setComparisonError(e.message)
      } })
    return () => controller.abort()
  }, [radio, current, week, requestKey, catalog])

  function changeModel(id) {
    setModelId(id); setError(''); setComparison(null); setComparisonError('')
    const next = catalog.models.find(m => m.model_id === id)
    if (!next.weeks.some(w => w.target_week_start === week)) setWeek(next.weeks[0].target_week_start)
  }

  function selectRadio(id) {
    setRadio(id || null); setComparison(null); setComparisonError('')
  }

  return <section className="research-spatial" aria-label="Investigación espacial A/B">
    <MethodNotice title="Investigación local · A/B">{experimentalWarning}</MethodNotice>
    {!catalog ? <div className="data-controls research-controls">
      {loadingCatalog && <p role="status">Consultando modelos experimentales…</p>}
      {!loadingCatalog && <button type="button" onClick={() => { setError(''); setLoadingCatalog(true); setLoadAttempt(n => n + 1) }}>Reintentar carga</button>}
    </div> : <div className="data-controls research-controls">
      <div className="week-control"><label htmlFor="research-model">Modelo experimental</label><select id="research-model" value={modelId} onChange={e => changeModel(e.target.value)}>{catalog.models.map(m => <option key={m.model_id} value={m.model_id}>Modelo {m.model_id}</option>)}</select></div>
      <div className="week-control"><label htmlFor="research-week">Semana epidemiológica objetivo</label><select id="research-week" value={week} onChange={e => { setWeek(e.target.value); setComparison(null); setError(''); setComparisonError('') }}>{model.weeks.map(w => <option key={w.target_week_start} value={w.target_week_start}>{w.target_epidemiological_year} · SE {w.target_epidemiological_week} · {w.target_week_start}</option>)}</select></div>
      <div className="week-control"><label htmlFor="research-radio">Radio censal</label><select id="research-radio" value={radio || ''} onChange={e => selectRadio(e.target.value)}><option value="">Seleccioná en el mapa o aquí</option>{geometry.features.map(f => <option key={f.properties.radio_id} value={f.properties.radio_id}>Radio {f.properties.radio_id}</option>)}</select></div>
    </div>}
    {error && <p role="alert">{error}</p>}
    {catalog && !current && !error && <p role="status">Consultando scores experimentales…</p>}
    {catalog && <>
      {current && <p className="research-provenance"><strong>Modelo {current.model_id}</strong> · SE {current.target_epidemiological_week}/{current.target_epidemiological_year} · {current.target_week_start} a {current.target_week_end} · {partitionNames[current.evaluation_partition]}</p>}
      <TerritorialMap geojson={mapGeometry || geometry} view="research" disclaimer={experimentalWarning} collectionKey={requestKey} selectedRadio={radio} onRadioSelect={selectRadio} showData={Boolean(current)} statusMessage={error || 'Consultando scores experimentales…'} researchDetails={<>
        <h3>Comparación A/B · mismo radio y semana</h3>
        {comparisonError ? <p role="alert">{comparisonError}</p> : !currentComparison ? <p role="status">Consultando comparación…</p> : <>
          <p className="muted">Probabilidad del modelo sin calibrar · escala 0 a 1</p>
          {['A', 'B'].map(id => { const c = currentComparison.results.find(c => c.model_id === id); const row = c?.rows?.[0]; return <div className="radio-score-pair" key={id}><span className={`model-label model-${id.toLowerCase()}`}>Modelo {id}:</span><strong>{row?.score_status === 'available' ? formatNumber(row.experimental_score, 6) : 'Sin resultado disponible'}</strong>{row?.score_status === 'available' && <span className="metric-track" aria-hidden="true"><span className={`metric-bar model-${id.toLowerCase()}`} style={{ width: `${row.experimental_score * 100}%` }} /></span>}</div> })}
          {!currentComparison.comparable && <p>No hay dos scores disponibles equivalentes para comparar.</p>}
        </>}
      </>} />
      <details className="research-technical"><summary>Identificadores y procedencia</summary>{catalog.models.map(m => <p key={m.model_id}><strong>Modelo {m.model_id}</strong> · {m.experiment_id}<small className="research-version">Versión: {m.training_version}</small></p>)}<p>Calendario argentino: ar-snvs-2020-2026-v1. Escenario de cobertura asumida: spatial_assumed_2024_v1. Consulta local de predicciones congeladas; no se ejecutan modelos.</p></details>
      <ExperimentalAnalysis catalog={catalog} radio={radio} week={week} />
    </>}
  </section>
}
