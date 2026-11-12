import { useEffect, useState } from 'react'
import { backtestSetup, backtestWeek } from '../services/backtestResults'
import { confusionNames, formatValue, qualityNames, statusNames } from '../services/backtestContract.mjs'
import { MethodNotice } from './SigardComponents'
import BacktestMaps from './BacktestMaps'
import BacktestHistory from './BacktestHistory'
import MLComparison from './MLComparison'
import { experimentalView } from '../services/backtestContract.mjs'
import './HistoricalBacktest.css'

function Metrics({ result, view }) {
  const m = result.metrics
  return <section className="bt-week-summary" aria-label="Resumen semanal">
    <h3>Referencia estadística · {result.disclosure?.mode === 'presentation' ? 'Subconjunto divulgable' : 'Resultado comparable'} · {m.n_comparable} radios</h3>
    <p>{result.disclosure?.mode === 'presentation' ? 'Métricas sólo de celdas divulgables; este subconjunto cambia por semana y no representa el rendimiento del estudio completo.' : 'Totales del conjunto con predicción y observación válidas. La selección de un radio se detalla debajo y en la evolución.'}</p>
    <dl className="bt-summary-values"><div><dt>Registros contabilizados</dt><dd>{formatValue(m.totals.observed)}</dd></div><div><dt>Cantidad estimada</dt><dd>{formatValue(m.totals.predicted)}</dd></div><div><dt>Persistencia de referencia</dt><dd>{formatValue(m.totals.baseline)}</dd></div></dl>
    {view === 'presence' ? <><div className="bt-confusion">{Object.entries(m.presence.confusion).map(([code, value]) => <p key={code}><strong>{formatValue(value, 0)}</strong><span>{code} · {confusionNames[code]}</span></p>)}</div>
      <p className="bt-metrics-inline">Brier: <strong>{formatValue(m.presence.brier, 4)}</strong> · AP: <strong>{formatValue(m.presence.average_precision, 4)}</strong> · ROC-AUC: <strong>{formatValue(m.presence.roc_auc, 4)}</strong> · Precisión: {formatValue(m.presence.precision, 4)} · Recall: {formatValue(m.presence.recall, 4)} · F1: {formatValue(m.presence.f1, 4)}</p>
    </> : <p className="bt-metrics-inline">MAE: <strong>{formatValue(m.quantity.mae, 4)}</strong> · RMSE: <strong>{formatValue(m.quantity.rmse, 4)}</strong> · Sesgo: <strong>{formatValue(m.quantity.bias, 4)}</strong> · MAE en ceros: {formatValue(m.quantity_zero.mae, 4)} · MAE con actividad: {formatValue(m.quantity_positive.mae, 4)}</p>}
    {result.department.reconciled && <p className="bt-reconciliation">Conciliación departamental: <strong>{formatValue(result.department.observed_total, 0)}</strong> registros = {formatValue(result.department.assigned_common_total, 0)} asignados al conjunto común + {formatValue(result.department.assigned_masked_total, 0)} en radios excluidos + {formatValue(result.department.unassigned_total, 0)} sin radio. La estimación no representa un total departamental completo.</p>}
  </section>
}

export default function HistoricalBacktest() {
  const [setup, setSetup] = useState(null)
  const [setupError, setSetupError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [target, setTarget] = useState('')
  const [view, setView] = useState('presence')
  const [source, setSource] = useState('ml')
  const [radio, setRadio] = useState('')
  const [disclosure, setDisclosure] = useState('presentation')
  const [response, setResponse] = useState(null)
  const selected = setup?.catalog.weeks.find(w => w.target_week === target)
  const key = `${target}/${attempt}/${disclosure}`
  const current = response?.key === key ? response : null
  useEffect(() => {
    const controller = new AbortController()
    backtestSetup(controller.signal).then(value => {
      if (controller.signal.aborted) return
      setSetup(value); setSetupError('')
      setTarget(t => t || value.catalog.weeks.find(w => w.availability_status === 'available')?.target_week || value.catalog.weeks[0].target_week)
    }).catch(error => { if (!controller.signal.aborted) setSetupError(error.message) })
    return () => controller.abort()
  }, [attempt])
  useEffect(() => {
    if (!setup || !selected) return
    const controller = new AbortController()
    backtestWeek(setup.catalog, selected, controller.signal, disclosure)
      .then(value => { if (!controller.signal.aborted) setResponse({ key, value }) })
      .catch(error => { if (!controller.signal.aborted) setResponse({ key, error: error.message }) })
    return () => controller.abort()
  }, [setup, selected, key, disclosure])
  function retry() { setSetupError(''); setAttempt(n => n + 1) }
  if (!setup) return <section className="historical-backtest" aria-label="Backtesting histórico">{setupError ? <div role="alert"><p>{setupError}</p><button type="button" onClick={retry}>Reintentar backtesting</button></div> : <p role="status">Verificando calendario y resultados históricos…</p>}</section>
  const years = [...new Set(setup.catalog.weeks.map(w => w.target_year))]
  const result = current?.value
  const displayResult = result ? experimentalView(result, source) : null
  const rows = displayResult?.rows.filter(r => !radio || r.radio_id === radio).sort((a, b) => disclosure === 'presentation' ? Number(b.availability_status === 'available') - Number(a.availability_status === 'available') : 0)
  const changeTarget = value => { setTarget(value); setResponse(null) }
  return <section className="historical-backtest" aria-label="Módulo predictivo experimental">
    <MethodNotice title="Reconstrucción retrospectiva · horizonte de una semana">Los resultados usan fechas de eventos y fuentes reconstruidas. No está acreditada la llegada histórica de todos los datos. Compara Random Forest y residual h=1 experimentales con las referencias estadísticas y los registros históricos. Ningún modelo está aprobado para operación ni emite alertas sanitarias.</MethodNotice>
    <div className="bt-disclosure"><label htmlFor="bt-disclosure">Acceso y divulgación</label><select id="bt-disclosure" value={disclosure} onChange={e => { setDisclosure(e.target.value); setResponse(null) }}><option value="presentation">Presentación protegida</option><option value="private">Investigación privada · valores exactos</option></select><p>{disclosure === 'presentation' ? 'Se protegen celdas con valores menores de 5, incluidos ceros, y sus complementos. Los totales completos quedan reservados a la investigación privada. Es una salvaguarda del prototipo, no una autorización institucional de publicación.' : 'Consulta exacta restringida al equipo autorizado en este equipo local. No proyectar, publicar ni compartir conteos pequeños. No habilita uso sanitario operativo.'}</p></div>
    <div className="bt-controls" aria-label="Selección histórica">
      <label>Año epidemiológico<select id="bt-year" value={selected?.target_year || ''} onChange={e => changeTarget(setup.catalog.weeks.find(w => w.target_year === Number(e.target.value)).target_week)}>{years.map(year => <option key={year} value={year}>{year}</option>)}</select></label>
      <label>Semana epidemiológica<select id="bt-week" value={target} onChange={e => changeTarget(e.target.value)}>{setup.catalog.weeks.filter(w => w.target_year === selected?.target_year).map(w => <option key={w.target_week} value={w.target_week}>SE {w.target_epi_week} · {statusNames[w.availability_status]} · ML {w.ml_availability?.[view] === 'available' ? 'disponible' : 'no disponible'}</option>)}</select></label>
      <label>Vista<select id="bt-view" value={view} onChange={e => setView(e.target.value)}><option value="presence">Dónde · Presencia</option><option value="quantity">Cuántos · Cantidad</option></select></label>
      <label>Predicción en mapa y detalle<select id="bt-source" value={source} onChange={e => setSource(e.target.value)}><option value="ml">ML experimental</option><option value="reference">Referencia estadística</option></select></label>
      <label>Unidad territorial<select id="bt-radio" value={radio} onChange={e => setRadio(e.target.value)}><option value="">Todos los radios</option>{setup.geometry.features.map(f => <option key={f.properties.radio_id} value={f.properties.radio_id}>{f.properties.radio_id}{!f.properties.common_mask ? ' · fuera del conjunto común' : ''}</option>)}</select></label>
    </div>
    {selected && <div className="bt-period"><p><strong>Objetivo: SE {selected.target_epi_week}/{selected.target_year}</strong><span>{selected.target_week} a {selected.target_end} · domingo a sábado</span></p><p><strong>Origen permitido</strong><span>{selected.origin_week} a {selected.origin_end} · último cierre previo</span></p><p><strong>{statusNames[selected.availability_status]}</strong><span>{selected.availability_status === 'available' ? 'Resultado offline verificado' : 'La ausencia de predicción no se convierte en cero'}</span></p></div>}
    {!current ? <p role="status">Consultando la semana seleccionada…</p> : current.error ? <div role="alert"><p>{current.error}</p><button type="button" onClick={retry}>Reintentar consulta</button></div> : <>
      {result.availability_status !== 'available' && <div className="bt-unavailable" role="status"><h3>Predicción no disponible</h3><p>{statusNames[result.availability_status]}. {result.availability_status === 'insufficient_training_support' ? 'No existe un resultado de la etapa 2 temporalmente válido para esta semana. Se conservan los registros conocidos.' : result.availability_status === 'outside_coverage' ? 'Las fuentes del proyecto no definen etiquetas para este período. Los valores permanecen no disponibles.' : 'La atribución territorial no permite una comparación completa.'}</p></div>}
      {result.availability_status === 'available' && (result.metrics.n_comparable ? <Metrics result={result} view={view} /> : <p className="bt-unavailable" role="status">No hay celdas comparables divulgables para esta selección. Los valores protegidos no representan ceros.</p>)}
      <MLComparison result={result} view={view} />
      <section className="bt-climate" aria-label="Contexto climático histórico"><h3>Clima en el último cierre permitido</h3><p>Un punto de referencia de La Rioja Capital; no son mediciones independientes por radio. Temperatura, humedad y precipitación se integraron al dataset y al contraste experimental, y ambos candidatos ML las reciben como predictores del origen o anteriores. Las referencias estadísticas no utilizan clima.</p>{result.climate?.availability_status === 'available' ? <><dl className="bt-summary-values"><div><dt>Temperatura media</dt><dd>{formatValue(result.climate.temperature_mean)} °C</dd></div><div><dt>Humedad relativa media</dt><dd>{formatValue(result.climate.humidity_mean)} %</dd></div><div><dt>Precipitación acumulada</dt><dd>{formatValue(result.climate.precipitation_total)} mm</dd></div></dl><p className="bt-caption">Período: {result.climate.origin_week} a {result.climate.period_end} · {result.climate.days} días. Reconstrucción por fechas; llegada histórica no acreditada.</p></> : <p>Contexto climático no disponible para este origen. Los faltantes no se sustituyen por cero.</p>}</section>
      <BacktestMaps geometry={setup.geometry} result={displayResult} source={source} view={view} radio={radio} onRadio={setRadio} />
      <section className="bt-territories" aria-label="Comparación por radio"><div className="bt-section-heading"><h3>{radio ? `Detalle del radio ${radio}` : 'Valores por radio censal'}</h3>{radio && <button type="button" onClick={() => setRadio('')}>Ver todos los radios</button>}</div>
        <p>Registros elegibles según la política vigente. En 2022, la positividad SIGARD es experimental y conserva la clasificación clínica original. Los ceros de semanas cubiertas proceden de la declaración metodológica del responsable.</p>
        <div className="bt-table-scroll bt-territory-table" tabIndex="0" role="region" aria-label="Comparación territorial detallada"><table><caption>{view === 'presence' ? 'Presencia prevista y registrada' : 'Cantidades y errores por unidad territorial'}</caption><thead><tr><th>Radio</th>{view === 'presence' ? <><th>Score referencia</th><th>Decisión referencia</th><th>{source === "ml" ? "Presencia ML" : "Presencia referencia"}</th><th>Registrada</th><th>Comparación</th><th>Score</th><th>Umbral</th></> : <><th>{source === "ml" ? "ML experimental" : "Referencia"}</th><th>Error referencia</th><th>Registrada</th><th>Diferencia</th><th>Error absoluto</th><th>Persistencia</th></>}<th>Estado</th><th>Calidad geográfica</th></tr></thead><tbody>{rows.map(r => <tr key={r.radio_id} className={radio === r.radio_id ? 'bt-selected' : ''}><th><button type="button" aria-pressed={radio === r.radio_id} onClick={() => setRadio(r.radio_id)}>{r.radio_id}</button></th>{view === 'presence' ? <><td>{formatValue(result.rows.find(x => x.radio_id === r.radio_id).predicted.presence_score, 4)}</td><td>{formatValue(result.rows.find(x => x.radio_id === r.radio_id).predicted.presence, 0)}</td><td>{r.predicted.presence === null ? 'No disponible' : r.predicted.presence ? 'Sí' : 'No'}</td><td>{r.observed.presence === null ? 'No disponible' : r.observed.presence ? 'Sí' : 'No'}</td><td>{confusionNames[r.confusion] || 'No comparable'}</td><td>{formatValue(r.predicted.presence_score, 4)}</td><td>{formatValue(r.presence_threshold, 4)}</td></> : <><td>{formatValue(r.predicted.quantity)}</td><td>{formatValue(result.rows.find(x => x.radio_id === r.radio_id).difference)}</td><td>{formatValue(r.observed.quantity, 0)}</td><td>{formatValue(r.difference)}</td><td>{formatValue(r.absolute_error)}</td><td>{formatValue(r.baseline.quantity)}</td></>}<td>{r.availability_status === "available" && source === "ml" && r.ml_availability?.[view] !== "available" ? "ML no disponible · referencia conservada" : statusNames[r.availability_status]}</td><td>{qualityNames[r.territorial_quality] || 'No acreditada'}</td></tr>)}</tbody></table></div>
        <p className="bt-caption">Scores sin calibración sanitaria acreditada. Las cantidades estimadas pueden ser decimales; se muestran redondeadas sólo para lectura. Métricas calculadas con valores completos.</p>
      </section>
    </>}
    {selected && <BacktestHistory key={`${selected.target_year}/${disclosure}`} catalog={setup.catalog} year={selected.target_year} radio={radio} disclosure={disclosure} />}
    <details className="bt-method"><summary>Métodos, versiones y límites de interpretación</summary><dl><dt>Dónde</dt><dd>Referencia territorial y estacional · {setup.metadata.selected_methods.presence}</dd><dt>Cuántos</dt><dd>Persistencia del último cierre · {setup.metadata.selected_methods.quantity}. Coincide con el baseline; no se presenta como ML entrenado.</dd><dt>Dataset</dt><dd>{setup.metadata.dataset_version}</dd><dt>Política epidemiológica</dt><dd>{setup.metadata.data_policy_version}</dd><dt>Versión territorial</dt><dd>{setup.metadata.territory_version} · 263 radios, 256 comparables</dd><dt>Campaña</dt><dd>{setup.metadata.campaign_version}</dd>{result?.fit_last_target_end && <><dt>Último objetivo utilizado en el ajuste del bloque</dt><dd>{result.fit_last_target_end} · purga de cuatro semanas antes del origen</dd></>}</dl><p>2024 es una comparación retrospectiva ya examinada, sin carácter de validación externa. Los registros son agregados de investigación, no episodios clínicos acreditados ni incidencia. No se publican personas ni coordenadas clínicas.</p><h4>Historial conservado</h4><p>A/B originales, Poisson previo y V3 con horizontes 2 y 4 quedan archivados. RF con clima y residual h=1 conservan el estado experimental_evaluated, sin promoción operativa. Este módulo consulta sus predicciones históricas guardadas; no ejecuta entrenamiento ni inferencia. A reentrenado y RF sin clima se conservan como evidencia comparativa.</p></details>
  </section>
}
