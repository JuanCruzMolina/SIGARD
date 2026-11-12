import { useEffect, useMemo, useState } from 'react'
import { TerritorialMap, MethodNotice } from './SigardComponents'
import { dateQueryReasons, experimentalWarning, joinComparisonGeometry } from '../services/experimentalContract.mjs'
import { researchCatalog, researchDate, researchDateQuery } from '../services/experimentalResults'
import { formatDifference, formatScore, partitionNames } from '../services/experimentalAnalysis.mjs'
import ExperimentalAnalysis from './ExperimentalAnalysis'

const modeNames = { A: 'Modelo A', B: 'Modelo B', difference: 'Diferencia B − A' }

function RadioComparison({ feature, current, weekMeta }) {
  const props = feature.properties
  return <>
    <p className="radio-target">Semana objetivo <strong>SE {weekMeta.target_epidemiological_week}/{weekMeta.target_epidemiological_year}</strong><span>{weekMeta.target_week_start} a {weekMeta.target_week_end}</span></p>
    <p className="muted">Scores brutos sin calibración epidemiológica acreditada · escala 0 a 1.</p>
    {['A', 'B'].map(id => {
      const row = props[id === 'A' ? 'model_a' : 'model_b']
      const available = row?.score_status === 'available'
      const reason = current[id]?.error || current[id]?.unavailable || (row ? 'Score congelado ausente' : 'Sin resultado para esta semana')
      return <div className="radio-score-pair" key={id}>
        <span className={`model-label model-${id.toLowerCase()}`}>Modelo {id}</span>
        <strong>{available ? formatScore(row.experimental_score) : 'No disponible'}</strong>
        {available && <small>{current[id]?.query?.result_type === 'experimental_inference' ? `Inferencia experimental nueva · corte: ${current[id].query.information_cutoff}` : 'Resultado congelado retrospectivo'}</small>}
        {available ? <span className="metric-track" aria-hidden="true"><span className={`metric-bar model-${id.toLowerCase()}`} style={{ width: `${row.experimental_score * 100}%` }} /></span> : <small>{reason}</small>}
        {id === 'B' && available && <small>Antecedentes conocidos: {row.data_availability?.known_lag_count ?? 'No informado'}/4 · disponibilidad retrospectiva.</small>}
      </div>
    })}
    <div className="radio-difference"><span>Diferencia B − A</span><strong>{formatDifference(props.difference)}</strong><small>{props.difference === null ? 'Requiere ambos scores disponibles para el mismo radio y semana.' : props.difference > 0 ? 'El score B es mayor que A.' : props.difference < 0 ? 'El score B es menor que A.' : 'Ambos scores son iguales.'}</small></div>
    <p className="analysis-footnote">La resta sólo compara scores disponibles para el mismo radio y semana. No representa casos, incidencia ni un cambio real del riesgo sanitario.</p>
    <a className="research-history-link" href="#radio-evolution">Consultar evolución de este radio</a>
  </>
}

export default function ExperimentalSpatial({ geometry }) {
  const [catalog, setCatalog] = useState(null)
  const [mode, setMode] = useState('A')
  const [date, setDate] = useState('')
  const [resolved, setResolved] = useState(null)
  const [query, setQuery] = useState(null)
  const [result, setResult] = useState(null)
  const [catalogError, setCatalogError] = useState('')
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [radio, setRadio] = useState(null)
  const weekMeta = resolved?.date === date ? resolved.value : null
  const dateError = resolved?.date === date ? resolved.error : ''
  const week = weekMeta?.target_week_start || ''
  const requestKey = query?.date === date ? `${date}/${query.attempt}` : ''
  const current = requestKey && result?.key === requestKey ? result.value : null
  const loading = Boolean(requestKey && !current)
  const mapGeometry = useMemo(() => joinComparisonGeometry(geometry, current || {}, week, mode), [geometry, current, week, mode])
  const selectedFeature = mapGeometry?.features.find(f => f.properties.radio_id === radio)
  const failed = current && ['A', 'B'].filter(id => current[id]?.error)
  const available = mapGeometry?.features.filter(f => mode === 'difference' ? f.properties.difference !== null : f.properties.score_status === 'available').length
  const statusMessage = dateError || (!date ? 'Seleccioná una fecha válida.' : !weekMeta ? 'Identificando semana epidemiológica…' : loading ? 'Consultando predicciones de A y B…' : !current ? 'Fecha seleccionada. Pulsá Consultar predicción.' : 'Consulta completada. Seleccioná un radio para ver el detalle.')

  function changeDate(value) {
    setDate(value)
    setQuery(null)
    setResult(null)
  }
  function consult() {
    setResult(null)
    setQuery(previous => ({ date, attempt: (previous?.attempt || 0) + 1 }))
  }

  useEffect(() => {
    const controller = new AbortController()
    researchCatalog(controller.signal)
      .then(c => {
        if (controller.signal.aborted) return
        setCatalog(c)
        setDate(previous => previous || [...c.models.flatMap(m => m.weeks)].sort((a, b) => a.target_week_start.localeCompare(b.target_week_start))[0].target_week_start)
        setCatalogError('')
      })
      .catch(e => { if (!controller.signal.aborted) setCatalogError(e.message) })
    return () => controller.abort()
  }, [loadAttempt])

  useEffect(() => {
    if (!date) return
    const controller = new AbortController()
    researchDate(date, controller.signal)
      .then(value => { if (!controller.signal.aborted) setResolved({ date, value }) })
      .catch(error => { if (!controller.signal.aborted) setResolved({ date, error: error.message }) })
    return () => controller.abort()
  }, [date, loadAttempt])

  useEffect(() => {
    if (!catalog || !requestKey || !weekMeta) return
    const controller = new AbortController()
    const models = catalog.models
    Promise.allSettled(models.map(m => researchDateQuery(m, date, geometry.features.map(f => f.properties.radio_id), weekMeta, controller.signal)))
      .then(responses => {
        if (controller.signal.aborted) return
        const value = Object.fromEntries(responses.map((response, i) => [models[i].model_id,
          response.status === 'fulfilled' ? { value: response.value.result, query: response.value,
            unavailable: response.value.blockers.map(code => dateQueryReasons[code]).join(' ') } : { error: response.reason.message }]))
        setResult({ key: requestKey, value })
      })
    return () => controller.abort()
  }, [catalog, date, weekMeta, geometry, requestKey])

  return <section className="research-spatial" aria-label="Investigación espacial A/B">
    <MethodNotice title="Investigación A/B · sólo consulta local">{experimentalWarning} Positivos provisionales y negativos asumidos experimentalmente; cobertura no acreditada, disponibilidad histórica incompleta y evaluación ya examinada.</MethodNotice>
    <details className="research-guide"><summary>Recorrido para explorar y presentar el panel</summary><ol>
      <li>Elegí una fecha y pulsá Consultar predicción. Se consulta la semana epidemiológica que contiene ese día.</li><li>Explorá el Modelo A y alterná al Modelo B: la semana y el radio se conservan.</li>
      <li>Elegí Diferencia B − A: azul indica B menor, ocre B mayor y blanco igualdad; gris indica ausencia.</li>
      <li>Seleccioná un radio en el mapa o con el teclado en el selector; consultá ambos scores y su evolución.</li>
      <li>Compará las métricas por partición y leé la metodología antes de interpretar los resultados.</li>
    </ol></details>
    <div className="research-model-context"><p><strong>Modelo A</strong> Variables territoriales y temporales.</p><p><strong>Modelo B</strong> Añade antecedentes experimentales de dengue de las cuatro semanas anteriores.</p><p>Ambos aprendieron de etiquetas epidemiológicas provisionales; A también utiliza esas etiquetas durante el entrenamiento.</p></div>
    {!catalog ? <div className="data-controls research-controls">
      {catalogError ? <><p role="alert">{catalogError}</p><button type="button" onClick={() => { setCatalogError(''); setLoadAttempt(n => n + 1) }}>Reintentar carga</button></> : <p role="status">Consultando modelos experimentales…</p>}
    </div> : <>
      {catalog.date_inference?.model_a_enabled && <p className="research-origin">Inferencia nueva A: {catalog.date_inference.target_week_start} a {catalog.date_inference.target_week_end}, con contexto censal fijo de 2022 disponible localmente desde {catalog.date_inference.context_available_at}. No requiere cerrar observaciones de la semana de origen. B necesita una fuente epidemiológica reciente verificable.</p>}
      <div className="data-controls research-controls" aria-label="Controles del panel experimental">
        <div className="week-control"><label htmlFor="research-model">Vista del mapa</label><select id="research-model" value={mode} onChange={e => setMode(e.target.value)}>{Object.entries(modeNames).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></div>
        <div className="week-control research-date-control"><label htmlFor="research-date">Fecha de la semana objetivo</label><input id="research-date" type="date" value={date} min={resolved?.value?.calendar_min} max={resolved?.value?.calendar_max} onChange={e => changeDate(e.target.value)} aria-describedby="research-date-help" /><small id="research-date-help">Todos los días de una semana consultan el mismo objetivo t+1.</small><button type="button" disabled={!weekMeta || loading} onClick={consult}>{loading ? 'Consultando…' : 'Consultar predicción'}</button></div>
        <div className="week-control"><label htmlFor="research-radio">Radio censal</label><select id="research-radio" value={radio || ''} onChange={e => setRadio(e.target.value || null)} aria-describedby="research-radio-help"><option value="">Seleccioná en el mapa o aquí</option>{geometry.features.map(f => <option key={f.properties.radio_id} value={f.properties.radio_id}>Radio {f.properties.radio_id}</option>)}</select><small id="research-radio-help">Mapa y selector comparten la selección.</small></div>
      </div>
      <div className="research-map-heading"><h2>Exploración territorial</h2><p className="research-provenance"><strong>{modeNames[mode]}</strong>{week && <> · SE {weekMeta.target_epidemiological_week}/{weekMeta.target_epidemiological_year} · {week} a {weekMeta.target_week_end}</>}</p>{week && <p className="research-origin">Origen t: {weekMeta.origin_week_start} a {weekMeta.origin_week_end}. Fin de origen: {weekMeta.calendar_cutoff}; este límite de calendario no es el corte informativo de la consulta.</p>}</div>
      <div className="research-availability" aria-live="polite" aria-busy={loading}>{!current ? <p role="status">{statusMessage}</p> : <><p>{available} de {geometry.features.length} radios con {mode === 'difference' ? 'ambos scores disponibles para la resta' : 'score disponible en esta vista'}. Gris: sin estimación; borde discontinuo: error de consulta.</p>{['A', 'B'].map(id => <p key={id}><strong>Modelo {id}:</strong> {current[id]?.value ? current[id].query?.result_type === 'experimental_inference' ? `Inferencia experimental nueva t+1 · no validada para uso sanitario · corte informativo: ${current[id].query.information_cutoff} · contexto fijo de 2022; no es población actual.` : `Resultado congelado · consulta retrospectiva · ${partitionNames[current[id].value.evaluation_partition]}` : current[id]?.unavailable || current[id]?.error || 'Modelo no disponible en esta sesión.'}</p>)}</>}</div>
      {dateError && <button type="button" onClick={() => setLoadAttempt(n => n + 1)}>Reintentar conexión</button>}
      {failed?.length > 0 && <div className="research-error"><p role="alert">{failed.map(id => `Modelo ${id}: ${current[id].error}`).join(' · ')}</p><button type="button" onClick={consult}>Reintentar consulta</button></div>}
      <TerritorialMap geojson={mapGeometry} view="research" researchMode={mode} collectionKey={`${date}/${week}/${requestKey}/${Boolean(current)}/${mode}`} selectedRadio={radio} onRadioSelect={setRadio} researchDetails={selectedFeature && current && week ? <RadioComparison feature={selectedFeature} current={current} weekMeta={weekMeta} /> : <p role="status">{statusMessage}</p>} />
      <ExperimentalAnalysis catalog={catalog} radio={radio} week={week} />
      <details className="research-technical"><summary>Identificadores y procedencia</summary>{catalog.models.map(m => <p key={m.model_id}><strong>Modelo {m.model_id}</strong> · {m.experiment_id}<small className="research-version">Versión: {m.training_version}</small></p>)}<p>Calendario argentino: ar-snvs-2020-2026-v1. Entrenamiento bajo escenario de cobertura asumida: spatial_assumed_2024_v1. Consulta local de resultados congelados e inferencia nueva cuando sus entradas están respaldadas. La diferencia sólo existe en memoria del navegador y no se guarda ni publica.</p></details>
    </>}
  </section>
}
