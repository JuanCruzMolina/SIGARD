import { HomeIcon, ShieldIcon } from './InfoIcons'

export default function PreventionGuide({ content }) {
  return <section id="prevenir" className="info-section" aria-labelledby="prevention-title">
    <div className="info-section-heading"><div><h2 id="prevention-title">Prevenir empieza por eliminar criaderos</h2></div><p>Revisá tu casa y los espacios cercanos cada semana, durante todo el año.</p></div>
    <div className="prevention-layout">
      <div className="prevention-principle"><HomeIcon className="info-icon large"/><strong>Sin agua acumulada, el mosquito no puede completar su ciclo.</strong><p>El descacharreo sostenido es la medida preventiva principal.</p></div>
      <ul className="action-list">{content.prevention.map((item) => <li key={item}><p>{item}</p></li>)}</ul>
    </div>
    <div className="vector-note"><ShieldIcon className="info-icon"/><div><h3>{content.vector_control.title}</h3><p>{content.vector_control.body}</p></div></div>
  </section>
}
