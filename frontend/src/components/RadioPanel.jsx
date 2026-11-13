import { useEffect, useRef, useState } from 'react'
import { backtestHistory } from '../services/backtestResults'
import { cellCategory, featureGroups, formatPlain, outcomeNames, statusPlain } from '../services/predictiveView.mjs'

function RecentHistory({ catalog, selected, radio, mode }) {
  const [state, setState] = useState(null)
  const weeks = catalog.weeks.filter(w => w.target_year === selected.target_year)
  const start = weeks[0].target_week, end = weeks.at(-1).target_week
  const key = `${radio}/${start}/${mode}`
  useEffect(() => {
    const controller = new AbortController()
    backtestHistory(catalog, start, end, radio, controller.signal, mode)
      .then(value => setState({ key, value })).catch(error => { if (!controller.signal.aborted) setState({ key, error: error.message }) })
    return () => controller.abort()
  }, [catalog, start, end, radio, mode, key])
  if (state?.key !== key) return <p className="pv-caption" role="status">Cargando historia del radio…</p>
  if (state.error) return <p className="pv-caption" role="alert">{state.error}</p>
  const index = state.value.series.findIndex(w => w.target_week === selected.target_week)
  const recent = state.value.series.slice(Math.max(0, index - 7), index + 1)
  const maximum = Math.max(1, ...recent.map(w => w.observed ?? 0))
  const known = recent.filter(w => w.observed !== null).length
  return <figure className="pv-spark">
    <svg viewBox={`0 0 ${recent.length * 14} 40`} role="img" aria-label={`Registros observados del radio en las últimas ${recent.length} semanas: ${recent.map(w => `SE ${w.target_epi_week} ${w.observed === null ? 'oculto' : formatPlain(w.observed)}`).join(', ')}`}>
      {recent.map((w, i) => w.observed === null
        ? <rect key={w.target_week} x={i * 14 + 2} y="36" width="10" height="2" className="pv-spark-hidden" />
        : <rect key={w.target_week} x={i * 14 + 2} y={38 - Math.max(2, w.observed / maximum * 34)} width="10" height={Math.max(2, w.observed / maximum * 34)} className={w.target_week === selected.target_week ? 'pv-spark-current' : 'pv-spark-bar'} />)}
    </svg>
    <figcaption>Últimas {recent.length} semanas · {known === recent.length ? 'todas visibles' : `${known} de ${recent.length} visibles${mode === 'presentation' ? '; las demás se ocultan por privacidad' : ''}`}</figcaption>
  </figure>
}

export default function RadioPanel({ radio, rows, sources, view, mode, result, catalog, selected, onClose }) {
  const heading = useRef(null)
  useEffect(() => { heading.current?.focus() }, [radio])
  useEffect(() => {
    const close = event => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close)
  }, [onClose])
  const base = rows.reference
  const category = cellCategory(base, view)
  const describe = (row, source) => {
    if (source.source === 'ml' && result.ml?.[view]?.availability_status !== 'available') return 'Sin predicción guardada'
    if (view === 'presence') return row.predicted.presence === null ? 'Sin dato' : row.predicted.presence ? 'Priorizado' : 'No priorizado'
    return row.predicted.quantity === null ? 'Sin dato' : `${formatPlain(row.predicted.quantity, 1)} registros`
  }
  const primary = sources[0]
  const features = primary.source === 'ml' ? featureGroups(result.ml?.[view]?.features) : []
  return <aside className="pv-panel" aria-labelledby="pv-panel-title">
    <div className="pv-panel-head"><h2 id="pv-panel-title" tabIndex="-1" ref={heading}>Radio censal {radio}</h2>
      <button type="button" className="pv-close" onClick={onClose} aria-label="Cerrar detalle del radio">✕</button></div>
    <p className="pv-panel-status">{statusPlain[base?.availability_status] || 'Sin dato'} · SE {selected.target_epi_week}/{selected.target_year}</p>
    {category === 'protected' ? <p className="pv-panel-message">Los valores de este radio esta semana son muy pequeños. Para proteger la privacidad no se muestran (un valor oculto no significa cero).</p>
      : category === 'outside' ? <p className="pv-panel-message">Este radio está fuera del universo común de comparación (256 radios); no tiene predicción.</p>
      : category === 'nodata' ? <p className="pv-panel-message">No hay predicción para este radio en esta semana.</p>
      : <dl className="pv-panel-values">
        {sources.map(s => <div key={s.source}><dt>Esperado · {s.label}</dt><dd>{describe(rows[s.source], s)}</dd></div>)}
        <div><dt>Ocurrido</dt><dd>{view === 'presence' ? base.observed.presence ? 'Tuvo registros' : 'Sin registros' : `${formatPlain(base.observed.quantity)} registros`}</dd></div>
        {view === 'presence' && rows[primary.source].confusion && <div><dt>Resultado · {primary.label}</dt><dd>{outcomeNames[rows[primary.source].confusion]}</dd></div>}
      </dl>}
    <h3>Historia reciente</h3>
    <RecentHistory catalog={catalog} selected={selected} radio={radio} mode={mode} />
    <h3>Qué información usa {primary.short}</h3>
    {features.length ? <ul className="pv-features">{features.map(f => <li key={f}>{f}</li>)}</ul> : <p>{primary.help}</p>}
    <p className="pv-caption">Describe datos de entrada, no causas. No se muestran los valores de cada variable para este radio.</p>
  </aside>
}
