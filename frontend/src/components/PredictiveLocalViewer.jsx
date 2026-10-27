import { useMemo, useState } from 'react'
import { TerritorialMap } from './SigardComponents'
import { joinCountGeometry } from '../services/predictivePresentation.mjs'

const number = value => Number.isFinite(value) ? new Intl.NumberFormat('es-AR', { maximumFractionDigits: 2 }).format(value) : 'No disponible'
const methodName = 'Persistencia con respaldo de media histórica'

export default function PredictiveLocalViewer({ payload }) {
  const [horizon, setHorizon] = useState(String(payload.initial_horizon))
  const [requestedDate, setRequestedDate] = useState(payload.initial_date)
  const [radio, setRadio] = useState('')
  const [onlyIncomplete, setOnlyIncomplete] = useState(false)
  const entries = payload.queries[horizon] || []
  // The calendar boundaries come from the existing Python planner, not ISO weeks.
  const result = entries.find(entry => requestedDate >= entry.target_week && requestedDate <= entry.target_end) || null
  const selected = result?.radios.find(row => row.radio_id === radio)
  const collection = useMemo(() => joinCountGeometry(payload.geometry, (payload.queries[horizon] || []).find(entry => requestedDate >= entry.target_week && requestedDate <= entry.target_end)), [payload, horizon, requestedDate])
  const rows = (result?.radios || []).filter(row => !onlyIncomplete || row.estimate_status !== 'available')
  function changeHorizon(value) {
    setHorizon(value)
    setRadio('')
  }
  return <main className="predictive-viewer">
    <header className="viewer-heading"><div><h1>SIGARD · Consulta territorial experimental</h1><p>{methodName}. Referencia estadística simple; no es un modelo avanzado de Machine Learning.</p></div><span className="local-label">Archivo privado · sin conexión</span></header>
    <p className="viewer-scope">Conteos de registros de un snapshot filtrado, con atribución territorial aproximada. Consulta histórica retrospectiva; los ceros registrados no acreditan ausencia epidemiológica.</p>
    <section className="viewer-controls" aria-label="Seleccionar consulta">
      <label htmlFor="prediction-date">Fecha histórica<input id="prediction-date" type="date" value={requestedDate} onChange={event => { setRequestedDate(event.target.value); setRadio('') }} /></label>
      <label htmlFor="prediction-horizon">Horizonte<select id="prediction-horizon" value={horizon} onChange={event => changeHorizon(event.target.value)}>{Object.keys(payload.queries).map(h => <option key={h} value={h}>t+{h} · {h === '1' ? 'una semana' : `${h} semanas`}</option>)}</select></label>
      <label htmlFor="prediction-week">Semanas admitidas<select id="prediction-week" value={result?.target_week || ''} onChange={event => { setRequestedDate(event.target.value); setRadio('') }}><option value="" disabled>Elegí una semana admitida</option>{entries.map(entry => <option key={entry.target_week} value={entry.target_week}>{entry.target_year} · SE {entry.target_week_number} · {entry.target_week}</option>)}</select></label>
    </section>
    <aside className="presence-notice"><strong>Probabilidad territorial en evaluación</strong><p>No disponible para alertas. Se conservan las métricas de investigación; esta demostración no muestra probabilidades ni puntajes de presencia.</p></aside>
    <section className="query-summary" aria-live="polite" aria-atomic="true">{result ? <>
      <h2>Semana objetivo: {result.target_week} a {result.target_end}</h2>
      <dl><div><dt>Total estimado del conjunto elegible</dt><dd id="territorial-total">{number(result.expected_eligible_total)} registros</dd></div><div><dt>Radios con estimación</dt><dd>{result.eligible_radios} de 256</dd></div><div><dt>Sin conteo reciente</dt><dd>{result.radios_with_incomplete_predictors} · respaldo histórico</dd></div><div><dt>Sin estimación</dt><dd>{result.radios_without_estimate}</dd></div></dl>
      <p>Origen: <strong>{result.origin_week}</strong> · Corte de predictores: <strong>{result.information_cutoff}</strong> · Horizonte: <strong>t+{horizon}</strong></p><p className="model-version">Versión: {result.model_version} · {methodName}</p>
    </> : <div role="status" className="unavailable-query"><h2>Datos insuficientes para esta fecha y horizonte</h2><p>Elegí una semana admitida. No hay observaciones recientes para generar predicciones de 2026. No se extrapolan semanas ni se conservan resultados anteriores en pantalla.</p></div>}</section>
    <TerritorialMap geojson={collection} view="snapshot_counts" disclaimer="Conteos experimentales, no incidencia ni riesgo de infección." collectionKey={`${horizon}/${result?.target_week || 'unavailable'}`} selectedRadio={radio} onRadioSelect={setRadio} showData={Boolean(result)} statusMessage="Datos insuficientes para la consulta seleccionada." snapshotDetails={selected && <>
      <dl><div><dt>Estimación de registros</dt><dd data-testid="radio-estimate">{number(selected.expected_count)}</dd></div><div><dt>Disponibilidad de predictores</dt><dd>{selected.estimate_status === 'insufficient_data' ? 'Información insuficiente: sin estimación.' : selected.estimate_status === 'available_with_historical_mean_fallback' ? 'Sin conteo reciente; se utiliza respaldo de media histórica.' : 'Conteo reciente disponible.'}</dd></div><div><dt>Variables disponibles</dt><dd>{selected.available_features}</dd></div><div><dt>Registros observados del snapshot</dt><dd>{number(selected.observed_snapshot_count)} · observación separada de la estimación</dd></div><div><dt>Calidad de la observación</dt><dd>{selected.observed_quality_state === 'assumed_snapshot_zero' ? 'Cero asumido del snapshot; no ausencia epidemiológica.' : selected.observed_quality_state === 'recorded_positive' ? 'Positivo registrado provisional.' : 'Observación desconocida o afectada por pendientes.'}</dd></div></dl>
      {selected.missing_features?.length > 0 && <details><summary>Predictores faltantes</summary><p>{selected.missing_features.join(', ')}</p></details>}
    </>} />
    {result && <details className="values-table"><summary>Consultar valores y estados de los 256 radios</summary><label className="incomplete-filter"><input type="checkbox" checked={onlyIncomplete} onChange={event => setOnlyIncomplete(event.target.checked)} />Mostrar información reciente insuficiente o sin estimación</label><div className="table-scroll"><table><caption>Conteos estimados y observaciones del snapshot · t+{horizon} · {result.target_week}</caption><thead><tr><th>Radio</th><th>Estimación</th><th>Observación</th><th>Disponibilidad</th></tr></thead><tbody>{rows.map(row => <tr key={row.radio_id}><th><button type="button" onClick={() => setRadio(row.radio_id)}>{row.radio_id}</button></th><td>{number(row.expected_count)}</td><td>{number(row.observed_snapshot_count)}</td><td>{row.estimate_status === 'available' ? 'Conteo reciente disponible' : row.estimate_status === 'insufficient_data' ? 'Sin estimación' : 'Respaldo histórico; sin conteo reciente'}</td></tr>)}</tbody></table></div></details>}
    <details className="comparison"><summary>Resultados científicos conservados</summary><p>Comparación descriptiva del período ya examinado. No selecciona modelos. Sesgo = estimación menos observación.</p><div className="table-scroll"><table><caption>Objetivos diferentes: no comparar directamente MAE condicional y MAE de grilla.</caption><thead><tr><th>Método y estado</th><th>Objetivo / conjunto</th><th>n</th><th>MAE</th><th>RMSE</th><th>Sesgo</th></tr></thead><tbody>{payload.comparison.map(row => <tr key={row.id}><th>{row.label}</th><td>{row.scope}</td><td>{row.n}</td><td>{number(row.mae)}</td><td>{number(row.rmse)}</td><td>{number(row.mean_bias)}</td></tr>)}</tbody></table></div><p>V1: modelo ML entrenado y conservado. GLM V2: candidato no promovido. Consulta territorial: persistencia y media histórica, sin promoción como ML avanzado. No hay un total observado completo de 256 radios donde persisten etiquetas desconocidas.</p></details>
    <footer>Mapa Leaflet · Uso privado local. V1 y V2 permanecen congeladas. No compartir este archivo ni publicarlo. No se generan alertas sanitarias.</footer>
  </main>
}
