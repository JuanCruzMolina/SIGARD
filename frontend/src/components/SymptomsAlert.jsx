import { AlertIcon, HealthIcon, PhoneIcon } from './InfoIcons'
import RestrictedMarkdown, { SectionSource } from './RestrictedMarkdown'
import { CONTENT_PENDING, INTRO_SLUGS } from '../services/preventionContent.mjs'

// Every health sentence comes from a published section (Administración → Contenido preventivo).
export default function SymptomsAlert({ sections, emergencyNumber }) {
  const symptoms = sections.sintomas
  const advice = sections['consejos-medicos']
  const warning = sections['signos-alarma']
  const heading = sections[INTRO_SLUGS.symptomsHeading]
  if (!symptoms && !advice && !warning) return null
  return <section id="sintomas" className="info-section symptoms-section" aria-labelledby="symptoms-title">
    <div className="info-section-heading"><div><h2 id="symptoms-title">{heading?.title || 'Síntomas'}</h2></div><div className="section-intro" data-slug={heading ? heading.slug : undefined}>{heading
      ? <><RestrictedMarkdown text={heading.body}/><SectionSource section={heading}/></>
      : <p className="content-pending" role="status">{CONTENT_PENDING}</p>}<p>SIGARD brinda orientación general; no realiza diagnósticos.</p></div></div>
    <div className="symptom-columns">
      {(symptoms || advice) && <article><HealthIcon className="info-icon"/>{symptoms && <><h3>{symptoms.title}</h3><RestrictedMarkdown text={symptoms.body}/><SectionSource section={symptoms}/></>}{advice && <div className="care-advice"><h4>{advice.title}</h4><RestrictedMarkdown text={advice.body}/><SectionSource section={advice}/></div>}</article>}
      <article className="alarm-panel"><AlertIcon className="info-icon"/>{warning && <><h3>{warning.title}</h3><RestrictedMarkdown text={warning.body}/><SectionSource section={warning}/></>}<a className="emergency-call" href={`tel:${emergencyNumber}`}><PhoneIcon className="button-icon"/>Llamar al {emergencyNumber}</a></article>
    </div>
  </section>
}
