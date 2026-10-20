import { useEffect, useState } from 'react'
import { researchEvaluation, researchHistory } from '../services/experimentalResults'
import { formatScore, metricDefinitions, partitionNames, scoreSegments } from '../services/experimentalAnalysis.mjs'

export function EvaluationComparison({ evaluation, partition, onPartitionChange }) {
  const selected = evaluation.partitions.find(p => p.partition === partition)
  return <>
    <div className="analysis-heading"><div><h3>Desempeño retrospectivo</h3><p>Comparación sobre las mismas etiquetas conocidas. Los desconocidos se excluyeron de las métricas.</p></div>
      <div className="week-control"><label htmlFor="analysis-partition">Partición de evaluación</label><select id="analysis-partition" value={partition} onChange={e => onPartitionChange(e.target.value)}>{evaluation.partitions.map(p => <option key={p.partition} value={p.partition}>{partitionNames[p.partition]}</option>)}</select></div>
    </div>
    <p className="analysis-scope">{selected.target_week_start} a {selected.target_week_end} · {selected.week_count} semanas · {selected.evaluated_radio_weeks.toLocaleString('es-AR')} filas radio–semana evaluadas · Umbral fijo 0,5</p>
    <div className="analysis-table-wrap"><table className="metric-comparison"><caption>Valores guardados en la evaluación comparativa. Barras en escala común de 0 a 1.</caption><thead><tr><th scope="col">Métrica</th>{['A', 'B'].map(id => <th scope="col" key={id}><span className={`model-label model-${id.toLowerCase()}`}>Modelo {id}</span></th>)}</tr></thead>
      <tbody>{metricDefinitions.map(metric => <tr key={metric.key}><th scope="row"><strong>{metric.label}</strong><span className="metric-direction">{metric.direction}</span><details><summary>Qué representa</summary><p>{metric.description}</p></details></th>{['A', 'B'].map(id => { const value = selected.models.find(m => m.model_id === id).metrics[metric.key]; return <td key={id}><span className="metric-value">{formatScore(value)}</span>{value !== null ? <span className="metric-track" aria-hidden="true"><span className={`metric-bar model-${id.toLowerCase()}`} style={{ width: `${value * 100}%` }} /></span> : <small>No definida en el informe</small>}</td> })}</tr>)}</tbody></table></div>
    <p className="analysis-footnote">Ninguna métrica por sí sola establece superioridad. La prueba ya fue examinada; estos resultados no son una validación epidemiológica independiente.</p>
  </>
}

export function RadioTimeline({ history, week }) {
  const comparisons = history.comparisons
  const first = Date.parse(comparisons[0].target_week_start + 'T00:00:00Z')
  const last = Date.parse(comparisons.at(-1).target_week_start + 'T00:00:00Z')
  const x = time => 58 + (time - first) / Math.max(last - first, 1) * 660
  const y = value => 218 - value * 180
  const currentX = x(Date.parse(week + 'T00:00:00Z'))
  const labels = comparisons.filter((_, i) => i === 0 || i === comparisons.length - 1 || i % 5 === 0)
  return <div className="radio-timeline">
    <div className="timeline-key"><span className="model-label model-a">Modelo A</span><span className="model-label model-b">Modelo B</span><span>Escala fija: 0 a 1</span></div>
    <p className="timeline-scroll-hint">Deslizá el gráfico horizontalmente para recorrer las semanas. También podés consultar los valores debajo.</p>
    <div className="timeline-plot" role="region" aria-label="Gráfico temporal con desplazamiento horizontal" tabIndex={0}><svg viewBox="0 0 760 265" role="img" aria-label={`Evolución de los scores experimentales A y B para el radio ${history.radio_censal}`}>
      <title>Scores congelados por semana objetivo</title><desc>Las líneas se interrumpen si no hay resultado o si faltan semanas. La línea vertical señala la semana elegida en el mapa.</desc>
      {[0, .25, .5, .75, 1].map(value => <g key={value}><line x1="58" x2="718" y1={y(value)} y2={y(value)} className="timeline-grid" /><text x="46" y={y(value) + 4} textAnchor="end">{String(value).replace('.', ',')}</text></g>)}
      {Number.isFinite(currentX) && currentX >= 58 && currentX <= 718 && <line x1={currentX} x2={currentX} y1="30" y2="224" className="timeline-selected" />}
      {['A', 'B'].map(id => <g key={id} className={`timeline-series model-${id.toLowerCase()}`}>{scoreSegments(comparisons, id).map((segment, i) => <g key={i}><polyline points={segment.map(point => `${x(point.time)},${y(point.score)}`).join(' ')} />{segment.map(point => <circle key={point.week} cx={x(point.time)} cy={y(point.score)} r={point.week === week ? 5 : 3}><title>{`Modelo ${id} · ${point.week} · ${formatScore(point.score)}`}</title></circle>)}</g>)}</g>)}
      {labels.map(c => <text key={c.target_week_start} x={x(Date.parse(c.target_week_start + 'T00:00:00Z'))} y="246" textAnchor="middle">{c.target_week_start.slice(8)}/{c.target_week_start.slice(5, 7)}</text>)}
    </svg></div>
    <p className="analysis-footnote">Score bruto del modelo, sin calibración clínica. Los huecos conservan resultados ausentes y semanas no calculadas, incluidas las purgadas. No son ceros.</p>
    <details className="analysis-values"><summary>Consultar valores por semana</summary><div className="analysis-table-wrap"><table><caption>Radio {history.radio_censal} · probabilidades del modelo sin calibrar</caption><thead><tr><th scope="col">Semana objetivo</th><th scope="col">Partición</th><th scope="col">Modelo A</th><th scope="col">Modelo B</th></tr></thead><tbody>{comparisons.map(c => { const meta = c.results[0]; return <tr key={c.target_week_start} aria-current={c.target_week_start === week ? 'date' : undefined}><th scope="row">SE {meta.target_epidemiological_week}/{meta.target_epidemiological_year}<small>{c.target_week_start}</small></th><td>{partitionNames[meta.evaluation_partition]}</td>{['A', 'B'].map(id => <td key={id}>{formatScore(c.results.find(m => m.model_id === id)?.rows[0].experimental_score)}</td>)}</tr> })}</tbody></table></div></details>
  </div>
}

export default function ExperimentalAnalysis({ catalog, radio, week }) {
  const [evaluation, setEvaluation] = useState(null)
  const [evaluationError, setEvaluationError] = useState('')
  const [partition, setPartition] = useState('test')
  const [history, setHistory] = useState(null)
  const [historyError, setHistoryError] = useState(null)
  const [showHistory, setShowHistory] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const currentHistory = history?.radio === radio ? history.value : null
  const currentError = historyError?.radio === radio ? historyError.message : ''

  useEffect(() => {
    const controller = new AbortController()
    researchEvaluation(catalog, controller.signal).then(value => { if (!controller.signal.aborted) { setEvaluation(value); setEvaluationError('') } })
      .catch(error => { if (!controller.signal.aborted) setEvaluationError(error.status === 404 ? 'Las métricas congeladas no están disponibles en el registro local. El mapa sigue disponible.' : error.message) })
    return () => controller.abort()
  }, [catalog, attempt])

  useEffect(() => {
    if (!radio || !showHistory) return
    const controller = new AbortController()
    researchHistory(catalog, radio, controller.signal).then(value => { if (!controller.signal.aborted) { setHistory({ radio, value }); setHistoryError(null) } })
      .catch(error => { if (!controller.signal.aborted) { setHistory(null); setHistoryError({ radio, message: error.message }) } })
    return () => controller.abort()
  }, [catalog, radio, showHistory, attempt])

  return <section className="experimental-analysis" aria-labelledby="analysis-title">
    <h2 id="analysis-title">Análisis de modelos</h2>
    {evaluationError ? <div className="analysis-message"><p role="alert">{evaluationError}</p><button type="button" onClick={() => setAttempt(n => n + 1)}>Reintentar análisis</button></div> : evaluation ? <EvaluationComparison evaluation={evaluation} partition={partition} onPartitionChange={setPartition} /> : <p role="status">Consultando métricas verificadas…</p>}
    <div className="analysis-temporal"><h3>Evolución del radio seleccionado</h3><p>{radio ? <>Radio <strong>{radio}</strong> · Ambos modelos sobre las mismas semanas objetivo.</> : 'Seleccioná un radio en el mapa o en el selector para consultar sus resultados a lo largo del tiempo.'}</p>
      {radio && (!showHistory ? <button type="button" onClick={() => setShowHistory(true)}>Ver evolución temporal</button> : currentError ? <div className="analysis-message"><p role="alert">{currentError}</p><button type="button" onClick={() => setAttempt(n => n + 1)}>Reintentar evolución</button></div> : currentHistory ? <RadioTimeline history={currentHistory} week={week} /> : <p role="status">Consultando las semanas calculadas de este radio…</p>)}
    </div>
    <details className="analysis-method"><summary>Cómo interpretar esta comparación</summary><p>Las predicciones experimentales son scores del modelo. Las etiquetas positivas representan registros epidemiológicos provisionales; las negativas son ausencias asumidas para el experimento. La evaluación retrospectiva compara ambos modelos frente a esas etiquetas, sin confirmar episodios ni medir riesgo clínico validado.</p><p>Las fechas, clasificaciones y ubicaciones conservan incertidumbre. Cobertura y disponibilidad histórica no están acreditadas. No se calcularon nuevas métricas en este panel.</p></details>
  </section>
}
