import { formatPlain, weekLabel, yearOptions } from '../services/predictiveView.mjs'

// Week selector: arrows, year, keyboard slider and a mini-histogram of records per week
// (protected mode: records in visible radios only; empty bars mean nothing disclosable).
export default function WeekTimeline({ weeks, selected, series, onSelect, onMostActive, mostActive, mode }) {
  const index = weeks.findIndex(w => w.target_week === selected.target_week)
  const yearWeeks = weeks.filter(w => w.target_year === selected.target_year)
  const position = yearWeeks.findIndex(w => w.target_week === selected.target_week)
  const byWeek = new Map((series || []).map(s => [s.target_week, s]))
  const values = yearWeeks.map(w => byWeek.get(w.target_week)?.observed ?? null)
  const maximum = Math.max(1, ...values.filter(v => v !== null))
  const activity = w => {
    const s = byWeek.get(w.target_week)
    if (!series) return 'cargando actividad'
    if (w.availability_status !== 'available') return 'sin predicción'
    return s?.n_comparable ? `${formatPlain(s.observed)} registros ${mode === 'presentation' ? 'en radios visibles' : 'en la ciudad'}` : 'sin datos divulgables'
  }
  const width = 100 / Math.max(1, yearWeeks.length)
  return <div className="pv-timeline">
    <div className="pv-week-nav">
      <button type="button" className="pv-arrow" aria-label="Semana anterior" disabled={index <= 0} onClick={() => onSelect(weeks[index - 1])}>◀</button>
      <p className="pv-week-label" aria-live="polite"><strong>SE {selected.target_epi_week} / {selected.target_year}</strong><span>{weekLabel(selected)}</span></p>
      <button type="button" className="pv-arrow" aria-label="Semana siguiente" disabled={index >= weeks.length - 1} onClick={() => onSelect(weeks[index + 1])}>▶</button>
      <label className="pv-year">Año<select id="pv-year" value={selected.target_year} onChange={e => onSelect(weeks.find(w => w.target_year === Number(e.target.value)), true)}>
        {yearOptions(weeks).map(o => <option key={o.year} value={o.year}>{o.label}</option>)}</select></label>
      <button type="button" className="pv-most-active" disabled={!mostActive} onClick={onMostActive}>Ir a la semana con más actividad</button>
    </div>
    <div className="pv-histogram">
      <svg viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true" className={series ? '' : 'pv-skeleton'}>
        {yearWeeks.map((w, i) => {
          const v = values[i]; const h = v === null ? 1.2 : Math.max(1.5, v / maximum * 22)
          return <rect key={w.target_week} x={i * width + width * .12} width={width * .76} y={24 - h} height={h}
            className={`pv-bar${v === null ? ' pv-bar-empty' : ''}${i === position ? ' pv-bar-selected' : ''}`}
            onClick={() => onSelect(w)}><title>SE {w.target_epi_week}: {activity(w)}</title></rect>
        })}
      </svg>
      <input id="pv-week" type="range" min="0" max={yearWeeks.length - 1} value={Math.max(0, position)} aria-label={`Semana epidemiológica de ${selected.target_year}`}
        aria-valuetext={`SE ${selected.target_epi_week} de ${selected.target_year}, ${weekLabel(selected)}: ${activity(selected)}`}
        onChange={e => onSelect(yearWeeks[Number(e.target.value)])} />
      <p className="pv-histogram-caption">{series ? mode === 'presentation' ? 'Barras: registros en radios visibles por semana. Las barras planas son semanas sin datos divulgables.' : 'Barras: registros de la ciudad por semana.' : 'Cargando actividad semanal…'}</p>
    </div>
  </div>
}
