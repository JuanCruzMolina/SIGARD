import { useEffect, useState } from 'react'
import { backtestHistory } from '../services/backtestResults'
import { formatValue, lineSegments, statusNames } from '../services/backtestContract.mjs'

function HistoryChart({ series }) {
  const maximum = Math.max(1, ...series.flatMap(w => [w.observed, w.predicted, w.baseline]).filter(v => v !== null))
  const x = i => 68 + i * 790 / Math.max(1, series.length - 1)
  const y = value => 218 - value / maximum * 170
  return <figure className="bt-chart"><div className="bt-chart-scroll" tabIndex="0" role="region" aria-label="Gráfico semanal desplazable"><svg viewBox="0 0 900 285" role="img" aria-labelledby="bt-chart-title bt-chart-description">
    <title id="bt-chart-title">Registros y cantidades estimadas por semana epidemiológica</title><desc id="bt-chart-description">Sin interpolar semanas desconocidas. Los valores y errores de cada semana están en la tabla siguiente. La estimación ML y la persistencia son series independientes.</desc>
    {[0, .5, 1].map(f => <g key={f}><line x1="68" x2="858" y1={y(maximum * f)} y2={y(maximum * f)} stroke="#d6e1de" /><text x="58" y={y(maximum * f) + 4} textAnchor="end">{formatValue(maximum * f, 1)}</text></g>)}
    <text x="68" y="25">Cantidad de registros</text>
    {['observed', 'baseline', 'predicted'].map(key => lineSegments(series, key, x, y).map((path, i) => <path key={`${key}/${i}`} d={path} className={`bt-line bt-line-${key}`} />))}
    {['observed', 'predicted'].map(key => series.map((w, i) => w[key] !== null && <circle key={`${key}/${w.target_week}`} cx={x(i)} cy={y(w[key])} r="2" fill={key === 'observed' ? '#087b75' : '#926716'} />))}
    {series.map((w, i) => (i === 0 || i === series.length - 1 || i % Math.max(1, Math.floor(series.length / 6)) === 0) && <text key={w.target_week} x={x(i)} y="243" textAnchor="middle">{w.target_epi_week}/{w.target_year}</text>)}
    <text x="463" y="274" textAnchor="middle">Semana epidemiológica argentina (SE/año)</text>
  </svg></div><figcaption><span className="bt-series observed">Registrados</span><span className="bt-series predicted">ML experimental</span><span className="bt-series baseline">Persistencia de referencia</span></figcaption></figure>
}

export default function BacktestHistory({ catalog, year, radio, disclosure = 'presentation' }) {
  const options = catalog.weeks
  const initial = options.filter(w => w.target_year === year)
  const [range, setRange] = useState({ start: initial[0].target_week, end: initial.at(-1).target_week })
  const [response, setResponse] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const key = `${range.start}/${range.end}/${radio || ''}/${attempt}/${disclosure}`
  const current = response?.key === key ? response : null
  useEffect(() => {
    const controller = new AbortController()
    backtestHistory(catalog, range.start, range.end, radio, controller.signal, disclosure)
      .then(value => { if (!controller.signal.aborted) setResponse({ key, value }) })
      .catch(error => { if (!controller.signal.aborted) setResponse({ key, error: error.message }) })
    return () => controller.abort()
  }, [catalog, range, radio, key, disclosure])
  const label = w => `SE ${w.target_epi_week}/${w.target_year} · ${statusNames[w.availability_status]}`
  return <section className="bt-history" aria-label="Evolución temporal">
    <h3>Evolución semanal</h3><p>{radio ? `Radio ${radio}` : disclosure === 'presentation' ? 'Suma del subconjunto divulgable' : 'Suma del conjunto común de 256 radios'} · Los cortes sin predicción válida conservan sus huecos. Las observaciones disponibles siguen visibles.</p>
    {disclosure === 'presentation' && <p className="bt-privacy-note">Presentación protegida: sumas y métricas sólo del subconjunto divulgable de cada semana. Su composición cambia; no representan totales completos ni las métricas científicas originales. Los intervalos sin celdas divulgables quedan vacíos.</p>}
    <div className="bt-controls bt-range"><label>Desde<select value={range.start} onChange={e => setRange(r => ({ start: e.target.value, end: r.end < e.target.value ? e.target.value : r.end }))}>{options.map(w => <option key={w.target_week} value={w.target_week}>{label(w)}</option>)}</select></label>
      <label>Hasta<select value={range.end} onChange={e => setRange(r => ({ end: e.target.value, start: r.start > e.target.value ? e.target.value : r.start }))}>{options.map(w => <option key={w.target_week} value={w.target_week}>{label(w)}</option>)}</select></label></div>
    {!current ? <p role="status">Consultando evolución semanal…</p> : current.error ? <div role="alert"><p>{current.error}</p><button type="button" onClick={() => setAttempt(n => n + 1)}>Reintentar evolución</button></div> : <>
      <HistoryChart series={current.value.series.map(w => ({ ...w, predicted: w.ml_predicted ?? null }))} />
      <p className="bt-metrics-inline">MAE referencia: <strong>{formatValue(current.value.metrics.quantity.mae, 4)}</strong> · RMSE: <strong>{formatValue(current.value.metrics.quantity.rmse, 4)}</strong> · Sesgo: <strong>{formatValue(current.value.metrics.quantity.bias, 4)}</strong> · Celdas comparables: {formatValue(current.value.metrics.n_comparable, 0)}</p>
      <div className="bt-table-scroll bt-weekly-table" tabIndex="0" role="region" aria-label="Errores semanales"><table><caption>Valores y errores por semana · sin redondear antes del cálculo</caption><thead><tr><th>Semana</th><th>Estado</th><th>Registrados</th><th>ML experimental</th><th>Persistencia</th><th>MAE ML por radio</th><th>MAE referencia</th><th>RMSE ML por radio</th><th>RMSE referencia</th><th>Sesgo por radio</th></tr></thead><tbody>{current.value.series.map(w => <tr key={w.target_week}><th>SE {w.target_epi_week}/{w.target_year}</th><td>{statusNames[w.availability_status]}</td><td>{formatValue(w.observed)}</td><td>{formatValue(w.ml_predicted)}</td><td>{formatValue(w.baseline)}</td><td>{formatValue(w.ml_metrics?.quantity.mae, 4)}</td><td>{formatValue(w.metrics.quantity.mae, 4)}</td><td>{formatValue(w.ml_metrics?.quantity.rmse, 4)}</td><td>{formatValue(w.metrics.quantity.rmse, 4)}</td><td>{formatValue(w.metrics.quantity.bias, 4)}</td></tr>)}</tbody></table></div>
      <details><summary>Resultados por año del intervalo</summary><div className="bt-table-scroll"><table><caption>Métricas calculadas sólo con celdas comparables</caption><thead><tr><th>Año</th><th>Celdas</th><th>Brier</th><th>MAE</th><th>MAE en ceros</th><th>MAE con actividad</th></tr></thead><tbody>{Object.entries(current.value.by_year).map(([year, m]) => <tr key={year}><th>{year}</th><td>{m.n_comparable}</td><td>{formatValue(m.presence.brier, 4)}</td><td>{formatValue(m.quantity.mae, 4)}</td><td>{formatValue(m.quantity_zero.mae, 4)}</td><td>{formatValue(m.quantity_positive.mae, 4)}</td></tr>)}</tbody></table></div></details>
    </>}
  </section>
}
