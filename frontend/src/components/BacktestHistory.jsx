import { formatValue, lineSegments } from '../services/backtestContract.mjs'
import { formatPlain } from '../services/predictiveView.mjs'

const SERIES = [
  { key: 'observed', label: 'Observados', className: 'observed' },
  { key: 'ml_predicted', label: 'Esperados por el modelo ML', className: 'predicted', ml: true },
  { key: 'predicted', label: 'Esperados por el método de referencia', className: 'baseline' },
]

// City evolution for the selected year. Unknown weeks break the lines; nothing is interpolated.
export default function BacktestHistory({ series, selected, onSelect, mode, hasML = true, mlKey = null }) {
  const lines = SERIES.filter(s => hasML || !s.ml)
  // ml_predicted is keyed by candidate; the line shows the selected count estimate only.
  const points = series.map(w => ({ ...w, ml_predicted: w.ml_predicted?.[mlKey] ?? null }))
  const maximum = Math.max(1, ...points.flatMap(w => lines.map(s => w[s.key])).filter(v => v !== null))
  const step = 800 / Math.max(1, points.length - 1)
  const x = i => 60 + i * step
  const y = value => 200 - value / maximum * 170
  const current = points.findIndex(w => w.target_week === selected.target_week)
  const empty = points.every(w => w.observed === null)
  return <section className="pv-evolution" aria-label="Evolución de la ciudad">
    <h2>Evolución de la ciudad en {selected.target_year}</h2>
    <p className="pv-caption">{mode === 'presentation' ? 'Suma de los radios visibles de cada semana (con 5 o más registros); no es el total de la ciudad y la cantidad de radios visibles cambia cada semana.' : 'Total de los 256 radios comparables por semana.'} Hacé clic en una semana para verla en el mapa.</p>
    {empty && <p className="pv-caption" role="status">Este año no tiene semanas con datos divulgables{mode === 'presentation' ? ' en modo protegido' : ''}.</p>}
    <figure className="bt-chart pv-chart">
      <svg viewBox="0 0 900 250" role="img" aria-labelledby="pv-chart-title pv-chart-desc">
        <title id="pv-chart-title">Registros observados y esperados por semana en {selected.target_year}</title>
        <desc id="pv-chart-desc">La semana SE {selected.target_epi_week} está marcada. Las semanas sin dato quedan como huecos. Los valores de cada semana están en Ver datos en tabla.</desc>
        {[0, .5, 1].map(f => <g key={f}><line x1="60" x2="860" y1={y(maximum * f)} y2={y(maximum * f)} stroke="#d6e1de" /><text x="52" y={y(maximum * f) + 4} textAnchor="end">{formatValue(maximum * f, 0)}</text></g>)}
        {current >= 0 && <rect x={x(current) - step / 2} y="24" width={Math.max(step, 6)} height="178" className="pv-chart-selected" />}
        {lines.map(s => lineSegments(points, s.key, x, y).map((path, i) => <path key={`${s.key}/${i}`} d={path} className={`bt-line bt-line-${s.className}`} />))}
        {lines.map(s => points.map((w, i) => w[s.key] !== null && <circle key={`${s.key}/${w.target_week}`} cx={x(i)} cy={y(w[s.key])} r="2.5" className={`pv-point-${s.className}`} />))}
        {points.map((w, i) => (i % 4 === 0 || i === points.length - 1) && <text key={w.target_week} x={x(i)} y="222" textAnchor="middle">{w.target_epi_week}</text>)}
        <text x="460" y="244" textAnchor="middle">Semana epidemiológica de {selected.target_year}</text>
        {points.map((w, i) => <rect key={`hit/${w.target_week}`} x={x(i) - step / 2} y="20" width={step} height="190" className="pv-chart-hit" onClick={() => onSelect(w)}>
          <title>SE {w.target_epi_week}: observados {formatPlain(w.observed)} · ML {formatPlain(w.ml_predicted, 1)} · referencia {formatPlain(w.predicted, 1)}</title></rect>)}
      </svg>
      <figcaption>{lines.map(s => <span key={s.key} className={`bt-series ${s.className}`}>{s.label}</span>)}<span className="pv-series-selected">Semana elegida</span></figcaption>
    </figure>
  </section>
}
