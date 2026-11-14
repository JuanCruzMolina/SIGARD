import { HomeIcon, ShieldIcon } from './InfoIcons'
import RestrictedMarkdown, { SectionSource } from './RestrictedMarkdown'

export default function PreventionGuide({ sections }) {
  const prevention = sections.prevencion
  const vector = sections['control-vectorial']
  if (!prevention && !vector) return null
  return <section id="prevenir" className="info-section" aria-labelledby="prevention-title">
    <div className="info-section-heading"><div><h2 id="prevention-title">{prevention?.title || 'Prevención'}</h2></div><p>Revisá tu casa y los espacios cercanos cada semana, durante todo el año.</p></div>
    {prevention && <div className="prevention-layout">
      <div className="prevention-principle"><HomeIcon className="info-icon large"/><strong>Sin agua acumulada, el mosquito no puede completar su ciclo.</strong><p>El descacharreo sostenido es la medida preventiva principal.</p></div>
      <div className="section-body"><RestrictedMarkdown text={prevention.body} listClassName="action-list" itemAsParagraph/><SectionSource section={prevention}/></div>
    </div>}
    {vector && <div className="vector-note"><ShieldIcon className="info-icon"/><div><h3>{vector.title}</h3><RestrictedMarkdown text={vector.body}/><SectionSource section={vector}/></div></div>}
  </section>
}
