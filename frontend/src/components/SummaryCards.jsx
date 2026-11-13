import { useId, useState } from 'react'
import { summaryCards } from '../services/predictiveView.mjs'

export function InfoTip({ label, children }) {
  const [open, setOpen] = useState(false); const id = useId()
  return <span className="pv-info">
    <button type="button" className="pv-info-button" aria-expanded={open} aria-controls={id} aria-label={label} onClick={() => setOpen(v => !v)}>i</button>
    {open && <span id={id} role="note" className="pv-info-text">{children}</span>}
  </span>
}

export default function SummaryCards({ result, view, primary, other, mode, onMostActive, mostActive }) {
  const summary = summaryCards({ result, view, primary, other, mode })
  if (summary.kind !== 'cards') return <section className="pv-empty" role="status" aria-label="Resumen de la semana">
    <h2>{summary.title}</h2><p>{summary.text}</p>
    {mostActive && <button type="button" onClick={onMostActive}>Ir a la semana con más actividad</button>}
  </section>
  return <section className="pv-summary" aria-label="Resumen de la semana">
    <div className="pv-cards">{summary.cards.map(card => <article key={card.id} className="pv-card" data-card={card.id}>
      <h3>{card.label}{card.help && <InfoTip label={`Qué es ${other?.label?.toLowerCase()}`}>{card.help}</InfoTip>}</h3>
      <p className="pv-card-value">{card.value}</p><p className="pv-card-detail">{card.detail}</p>
    </article>)}</div>
    <p className={`pv-note${mode === 'presentation' ? ' pv-note-protected' : ''}`}>{summary.note}</p>
  </section>
}
