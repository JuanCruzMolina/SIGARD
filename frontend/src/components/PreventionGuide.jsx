import { HomeIcon, ShieldIcon } from './InfoIcons'
import RestrictedMarkdown, { SectionSource } from './RestrictedMarkdown'
import { CONTENT_PENDING, INTRO_SLUGS } from '../services/preventionContent.mjs'

// Every health sentence comes from a published section (Administración → Contenido preventivo).
export default function PreventionGuide({ sections }) {
  const prevention = sections.prevencion
  const vector = sections['control-vectorial']
  const summary = sections[INTRO_SLUGS.preventionSummary]
  const principle = sections[INTRO_SLUGS.preventionPrinciple]
  if (!prevention && !vector) return null
  return <section id="prevenir" className="info-section" aria-labelledby="prevention-title">
    <div className="info-section-heading"><div><h2 id="prevention-title">{prevention?.title || 'Prevención'}</h2></div>{summary && <div className="section-intro" data-slug={summary.slug}><RestrictedMarkdown text={summary.body}/><SectionSource section={summary}/></div>}</div>
    {prevention && <div className="prevention-layout">
      <div className="prevention-principle" data-slug={principle ? principle.slug : undefined}><HomeIcon className="info-icon large"/>{principle
        ? <><strong>{principle.title}</strong><RestrictedMarkdown text={principle.body}/><SectionSource section={principle}/></>
        : <p className="content-pending" role="status">{CONTENT_PENDING}</p>}</div>
      <div className="section-body"><RestrictedMarkdown text={prevention.body} listClassName="action-list" itemAsParagraph/><SectionSource section={prevention}/></div>
    </div>}
    {vector && <div className="vector-note"><ShieldIcon className="info-icon"/><div><h3>{vector.title}</h3><RestrictedMarkdown text={vector.body}/><SectionSource section={vector}/></div></div>}
  </section>
}
