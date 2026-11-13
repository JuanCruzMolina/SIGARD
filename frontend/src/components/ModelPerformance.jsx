import { Fragment } from 'react'
import { confusionNames, formatValue } from '../services/backtestContract.mjs'
import { formatPlain, globalVerdict } from '../services/predictiveView.mjs'
import MLComparison from './MLComparison'

// Technical weekly summary (previous main block), now only under "Ver métricas técnicas".
function TechnicalWeek({ result, view }) {
  const m = result.metrics
  return <section className="bt-week-summary" aria-label="Métricas técnicas de la semana">
    <h4>Método de referencia · {result.disclosure?.mode === 'presentation' ? 'Subconjunto divulgable' : 'Resultado comparable'} · {m.n_comparable} radios</h4>
    <p>{result.disclosure?.mode === 'presentation' ? 'Métricas sólo de celdas divulgables; este subconjunto cambia por semana y no representa el rendimiento del estudio completo.' : 'Totales del conjunto con predicción y observación válidas.'}</p>
    <dl className="bt-summary-values"><div><dt>Registros contabilizados</dt><dd>{formatValue(m.totals.observed)}</dd></div><div><dt>Cantidad estimada</dt><dd>{formatValue(m.totals.predicted)}</dd></div><div><dt>Persistencia de referencia</dt><dd>{formatValue(m.totals.baseline)}</dd></div></dl>
    {view === 'presence' ? <><div className="bt-confusion">{Object.entries(m.presence.confusion).map(([code, value]) => <p key={code}><strong>{formatValue(value, 0)}</strong><span>{code} · {confusionNames[code]}</span></p>)}</div>
      <p className="bt-metrics-inline">Brier: <strong>{formatValue(m.presence.brier, 4)}</strong> · AP: <strong>{formatValue(m.presence.average_precision, 4)}</strong> · ROC-AUC: <strong>{formatValue(m.presence.roc_auc, 4)}</strong> · Precisión: {formatValue(m.presence.precision, 4)} · Recall: {formatValue(m.presence.recall, 4)} · F1: {formatValue(m.presence.f1, 4)}</p>
    </> : <p className="bt-metrics-inline">MAE: <strong>{formatValue(m.quantity.mae, 4)}</strong> · RMSE: <strong>{formatValue(m.quantity.rmse, 4)}</strong> · Sesgo: <strong>{formatValue(m.quantity.bias, 4)}</strong> · MAE en ceros: {formatValue(m.quantity_zero.mae, 4)} · MAE con actividad: {formatValue(m.quantity_positive.mae, 4)}</p>}
    {result.department?.reconciled && <p className="bt-reconciliation">Conciliación departamental: <strong>{formatValue(result.department.observed_total, 0)}</strong> registros = {formatValue(result.department.assigned_common_total, 0)} asignados al conjunto común + {formatValue(result.department.assigned_masked_total, 0)} en radios excluidos + {formatValue(result.department.unassigned_total, 0)} sin radio.</p>}
  </section>
}

function YearRow({ year, reference, ml, view }) {
  const c = m => m?.presence?.confusion
  const cell = m => {
    if (!m?.n_comparable) return '—'
    if (view === 'quantity') return formatPlain(m.quantity.mae, 3)
    const k = c(m); return `${formatPlain(k.TP)} de ${formatPlain(k.TP + k.FN)} · ${formatPlain(k.FP)} falsas alarmas`
  }
  return <tr><th scope="row">{year}</th><td>{cell(ml)}</td><td>{cell(reference)}</td></tr>
}

export default function ModelPerformance({ metadata, mode, view, histories, result }) {
  const verdict = globalVerdict(metadata)
  const years = Object.keys(histories).sort()
  return <div className="pv-performance">
    <h3>Resultado del estudio</h3>
    {verdict ? <>{verdict.text.map(t => <p key={t}>{t}</p>)}<p className="pv-caption">Fuente: {verdict.source}.</p></>
      : <p>Los modelos mostrados no tienen un cierre documentado en esta versión del módulo.</p>}
    <h3>Por año {view === 'presence' ? '(¿Dónde?)' : '(¿Cuántos?)'}</h3>
    {mode === 'presentation'
      ? <p>Las cifras por año sólo se muestran en el modo privado: en modo protegido sólo se ven radios con 5 o más registros, y ese subconjunto no permite medir el desempeño.</p>
      : years.length ? <div className="bt-table-scroll"><table>
        <caption>{view === 'presence' ? 'Radios con registros que cada método anticipó, y falsas alarmas, sumando las semanas de cada año.' : 'Diferencia promedio por radio entre registros esperados y observados.'} Años cargados en esta sesión.</caption>
        <thead><tr><th scope="col">Año</th><th scope="col">Modelo ML</th><th scope="col">Método de referencia</th></tr></thead>
        <tbody>{years.map(y => <YearRow key={y} year={y} view={view} reference={histories[y].by_year?.[y]} ml={histories[y].ml_by_year?.[y]} />)}</tbody></table></div>
      : <p role="status">Cargando resultados por año…</p>}
    {result && <details className="pv-technical"><summary>Ver métricas técnicas</summary>
      <p className="pv-caption">Para el tribunal: métricas de la semana elegida con su nomenclatura técnica (TP = acierto, FP = falsa alarma, FN = no anticipado, TN = correctamente sin alerta).</p>
      {result.availability_status === 'available' && result.metrics.n_comparable > 0 && <TechnicalWeek result={result} view={view} />}
      <MLComparison result={result} view={view} />
      <details className="bt-method"><summary>Métodos y versiones</summary><dl>
        <dt>¿Dónde? · referencia</dt><dd>{metadata.method_labels?.presence} · {metadata.selected_methods.presence}</dd>
        <dt>¿Cuántos? · referencia</dt><dd>{metadata.method_labels?.quantity} · {metadata.selected_methods.quantity}</dd>
        {Object.entries(metadata.experimental_methods || {}).map(([k, v]) => <Fragment key={k}><dt>{k === 'presence' ? '¿Dónde?' : '¿Cuántos?'} · ML experimental</dt><dd>{v}</dd></Fragment>)}
        <dt>Dataset</dt><dd>{metadata.dataset_version}</dd><dt>Política epidemiológica</dt><dd>{metadata.data_policy_version}</dd>
        <dt>Versión territorial</dt><dd>{metadata.territory_version} · 263 radios, 256 comparables</dd><dt>Campaña</dt><dd>{metadata.campaign_version}</dd>
        {result.fit_last_target_end && <><dt>Último objetivo usado en el ajuste</dt><dd>{result.fit_last_target_end} · purga de cuatro semanas antes del origen</dd></>}
      </dl></details>
    </details>}
  </div>
}
