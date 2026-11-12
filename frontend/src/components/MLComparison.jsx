import { formatValue } from '../services/backtestContract.mjs'

export default function MLComparison({ result, view }) {
  const model = result.ml?.[view]
  const ml = result.ml_metrics
  const reference = result.metrics
  const keys = view === 'presence'
    ? ['brier', 'average_precision', 'roc_auc', 'precision', 'recall', 'f1'] : ['mae', 'rmse', 'bias']
  const labels = { brier: 'Brier', average_precision: 'Average Precision', roc_auc: 'ROC-AUC', precision: 'Precisión', recall: 'Recall', f1: 'F1', mae: 'MAE', rmse: 'RMSE', bias: 'Sesgo' }
  return <section className="bt-ml-comparison" aria-label="ML frente a referencia">
    <h3>ML experimental frente a referencia estadística</h3>
    <p>{model?.availability_status === 'available'
      ? `${model.method} · experimental_evaluated · ajuste hasta ${model.fit_last_target_end}. No aprobado para operación.`
      : model?.reason === 'ml_integrity_or_compatibility_blocked'
        ? 'Predicción ML no disponible: la verificación de integridad o compatibilidad bloqueó el resultado. La referencia estadística se conserva.'
        : 'Predicción ML no disponible: no existe una salida guardada compatible para esta semana. La referencia estadística se conserva cuando está disponible.'}</p>
    {view === 'quantity' && <dl className="bt-summary-values"><div><dt>Cantidad ML experimental</dt><dd>{formatValue(ml?.totals.predicted)}</dd></div><div><dt>Registros comparables con ML</dt><dd>{formatValue(ml?.totals.observed)}</dd></div><div><dt>Persistencia comparable con ML</dt><dd>{formatValue(ml?.totals.baseline)}</dd></div></dl>}
    <div className="bt-table-scroll"><table><caption>Mismas celdas divulgables; sin interpretar valores protegidos como ceros</caption><thead><tr><th>Métrica</th><th>ML experimental</th><th>Referencia</th></tr></thead><tbody>
      {keys.map(k => <tr key={k}><th>{labels[k]}</th><td>{formatValue(ml?.[view]?.[k], 4)}</td><td>{formatValue(reference[view][k], 4)}</td></tr>)}
      {view === 'presence' && ['TP', 'FP', 'FN', 'TN'].map(k => <tr key={k}><th>{k}</th><td>{ml?.presence.n ? formatValue(ml.presence.confusion[k], 0) : 'No disponible'}</td><td>{formatValue(reference.presence.confusion[k], 0)}</td></tr>)}
    </tbody></table></div>
    {model?.availability_status === 'available' && <details><summary>Modelo, variables y calibración descriptiva</summary>
      <p className="research-provenance">Versión: {model.model_version}<br />SHA-256: {model.artifact_sha256}</p>
      <p>Variables efectivas de entrada: {model.features.join(', ')}.</p>
      <p>Open-Meteo: temperatura, humedad y precipitación del origen y semanas anteriores. Un punto de Capital. Llegada histórica no acreditada; los faltantes no se imputan a cero. Población y densidad permanecen sin disponibilidad temporal acreditada.</p>
      <p>{view === 'presence' ? 'La ablación anterior redujo Brier frente al RF sin clima, pero no superó la referencia en desarrollo y empeoró AP/F1 globales. Score sin calibración sanitaria acreditada.' : 'El candidato recibe variables climáticas; su aporte incremental en cantidad no está demostrado.'}</p>
      {view === 'presence' && <div className="bt-table-scroll"><table><caption>Calibración descriptiva del subconjunto visible; no es un ajuste</caption><thead><tr><th>Intervalo</th><th>N</th><th>Score medio</th><th>Fracción registrada</th></tr></thead><tbody>{(ml?.presence.calibration || []).map(b => <tr key={b.lower}><td>{b.lower}–{b.upper}</td><td>{b.n}</td><td>{formatValue(b.score_mean, 4)}</td><td>{formatValue(b.observed_fraction, 4)}</td></tr>)}</tbody></table></div>}
    </details>}
  </section>
}
