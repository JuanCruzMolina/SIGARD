import { AlertIcon, HealthIcon, PhoneIcon } from './InfoIcons'

export default function SymptomsAlert({ content }) {
  return <section id="sintomas" className="info-section symptoms-section" aria-labelledby="symptoms-title">
    <div className="info-section-heading"><div><h2 id="symptoms-title">Reconocé los síntomas y actuá a tiempo</h2></div><p>SIGARD brinda orientación general; no realiza diagnósticos.</p></div>
    <div className="symptom-columns">
      <article><HealthIcon className="info-icon"/><h3>Síntomas compatibles</h3><ul>{content.symptoms.map((item) => <li key={item}>{item}</li>)}</ul><div className="care-advice">{content.medical_advice.map((item) => <p key={item}>{item}</p>)}</div></article>
      <article className="alarm-panel"><AlertIcon className="info-icon"/><h3>Signos de alarma</h3><ul>{content.warning_signs.map((item) => <li key={item}>{item}</li>)}</ul><a className="emergency-call" href={`tel:${content.emergency_number}`}><PhoneIcon className="button-icon"/>Llamar al {content.emergency_number}</a></article>
    </div>
  </section>
}
