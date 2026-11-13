import { useState } from 'react'
import { cellCategory, formatPlain, outcomeNames, statusPlain } from '../services/predictiveView.mjs'

const yesNo = value => value === null || value === undefined ? '—' : value ? 'Sí' : 'No'

function radioColumns(view, sources) {
  const [primary] = sources
  const cols = [{ key: 'radio', label: 'Radio', value: r => r.radio_id }, { key: 'status', label: 'Estado', value: r => statusPlain[r.base.availability_status] }]
  if (view === 'presence') {
    for (const s of sources) cols.push({ key: `p-${s.source}`, label: `Priorizado · ${s.label}`, value: r => yesNo(r[s.source].predicted.presence) })
    cols.push({ key: 'observed', label: 'Tuvo registros', value: r => yesNo(r.base.observed.presence) })
    cols.push({ key: 'outcome', label: `Resultado · ${primary.label}`, value: r => outcomeNames[r[primary.source].confusion] || '—' })
  } else {
    for (const s of sources) cols.push({ key: `q-${s.source}`, label: `Esperados · ${s.label}`, value: r => r[s.source].predicted.quantity, number: 1 })
    cols.push({ key: 'observed', label: 'Observados', value: r => r.base.observed.quantity, number: 0 })
    cols.push({ key: 'difference', label: `Diferencia · ${primary.label}`, value: r => r[primary.source].difference, number: 1, signed: true })
  }
  return cols
}
const weekColumns = mode => [
  { key: 'week', label: 'Semana', value: w => `SE ${w.target_epi_week}/${w.target_year}`, sortValue: w => w.target_week },
  { key: 'visible', label: mode === 'presentation' ? 'Radios visibles' : 'Radios comparables', value: w => w.n_comparable, number: 0 },
  { key: 'observed', label: 'Observados', value: w => w.observed, number: 0 },
  { key: 'ml', label: 'Esperados · Modelo ML', value: w => w.ml_predicted ?? null, number: 1 },
  { key: 'reference', label: 'Esperados · Método de referencia', value: w => w.predicted, number: 1 },
]

export default function DataTable({ rows, series, view, sources, mode }) {
  const [by, setBy] = useState('radio')
  const [sort, setSort] = useState({ key: null, dir: 1 })
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)
  const columns = by === 'radio' ? radioColumns(view, sources) : weekColumns(mode)
  const items = by === 'radio' ? rows : series || []
  const hasData = by === 'radio' ? r => ['TP', 'FP', 'FN', 'TN', 'value'].includes(cellCategory(r.base, view)) : w => w.n_comparable > 0
  const filtered = items.filter(item => (showAll || hasData(item)) && (!query || (by === 'radio' ? item.radio_id : `${item.target_epi_week}`).includes(query.trim())))
  const hidden = items.length - items.filter(hasData).length
  const column = columns.find(c => c.key === sort.key)
  const sorted = column ? [...filtered].sort((a, b) => {
    const va = (column.sortValue || column.value)(a), vb = (column.sortValue || column.value)(b)
    if (va === null || va === undefined) return 1; if (vb === null || vb === undefined) return -1
    return (va > vb ? 1 : va < vb ? -1 : 0) * sort.dir
  }) : filtered
  const show = (c, item) => { const v = c.value(item); return c.number === undefined ? v : v === null || v === undefined ? '—' : `${c.signed && v > 0 ? '+' : ''}${formatPlain(v, c.number)}` }
  return <div className="pv-table">
    <div className="pv-table-controls">
      <div className="pv-segmented" role="group" aria-label="Ver la tabla por">
        <button type="button" aria-pressed={by === 'radio'} onClick={() => { setBy('radio'); setSort({ key: null, dir: 1 }) }}>Por radio</button>
        <button type="button" aria-pressed={by === 'week'} onClick={() => { setBy('week'); setSort({ key: null, dir: 1 }) }}>Por semana</button>
      </div>
      <label>{by === 'radio' ? 'Buscar radio' : 'Buscar semana'}<input type="search" value={query} onChange={e => setQuery(e.target.value)} inputMode="numeric" /></label>
      <label className="pv-check"><input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />{by === 'radio' ? 'Mostrar también radios sin datos' : 'Mostrar también semanas sin datos'}</label>
    </div>
    {!showAll && hidden > 0 && <p className="pv-caption">{hidden} {by === 'radio' ? 'radios sin datos visibles (protegidos, fuera del universo común o sin predicción) se ocultan de la tabla.' : 'semanas sin datos divulgables se ocultan de la tabla.'}</p>}
    {sorted.length ? <div className="bt-table-scroll pv-table-scroll" tabIndex="0" role="region" aria-label="Datos en tabla">
      <table><thead><tr>{columns.map(c => <th key={c.key} scope="col" aria-sort={sort.key === c.key ? sort.dir > 0 ? 'ascending' : 'descending' : 'none'}>
        <button type="button" className="pv-sort" onClick={() => setSort(s => ({ key: c.key, dir: s.key === c.key ? -s.dir : 1 }))}>{c.label}</button></th>)}</tr></thead>
        <tbody>{sorted.map(item => <tr key={by === 'radio' ? item.radio_id : item.target_week}>{columns.map((c, i) => i === 0 ? <th key={c.key} scope="row">{show(c, item)}</th> : <td key={c.key}>{show(c, item)}</td>)}</tr>)}</tbody></table>
    </div> : <p role="status">No hay filas con datos para mostrar.</p>}
  </div>
}
