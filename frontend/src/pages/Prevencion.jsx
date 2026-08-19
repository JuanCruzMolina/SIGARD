import { useEffect, useState } from 'react'
import CitizenReportForm from '../components/CitizenReportForm'
import HealthFacilitiesMap from '../components/HealthFacilitiesMap'
import { HealthIcon, HomeIcon, PhoneIcon, PinIcon } from '../components/InfoIcons'
import PreventionGuide from '../components/PreventionGuide'
import ReportStatusLookup from '../components/ReportStatusLookup'
import SymptomsAlert from '../components/SymptomsAlert'
import { loadPreventionData, PREVENTION_DATA_ERROR } from '../services/preventionData'
import '../Prevention.css'

export default function Prevencion() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    loadPreventionData().then(setData).catch(() => setError(PREVENTION_DATA_ERROR))
  }, [])

  if (error) {
    return <main className="error-state" role="alert"><h1>Prevención y ayuda</h1><p>{error}</p></main>
  }
  if (!data) {
    return <main className="loading-state"><span className="spinner" />Cargando información sanitaria…</main>
  }

  const { content, facilities } = data
  return (
    <div className="prevention-page">
      <section className="prevention-hero">
        <div className="hero-content">
          <h1>Cuidarnos del dengue empieza en cada casa y cada barrio</h1>
          <p>Encontrá acciones claras, centros públicos de salud y un canal anónimo para registrar problemas que requieran evaluación.</p>
          <div className="hero-actions">
            <a className="hero-primary" href="#prevenir"><HomeIcon className="button-icon" />Prevenir en casa</a>
            <a href="#centros"><HealthIcon className="button-icon" />Buscar un centro</a>
            <a href="#reportar"><PinIcon className="button-icon" />Reportar un problema</a>
          </div>
        </div>
        <aside className="emergency-panel">
          <span>Ante signos de alarma</span>
          <strong>No esperes. Buscá atención urgente.</strong>
          <a href={`tel:${content.emergency_number}`}><PhoneIcon className="button-icon" />Llamar al {content.emergency_number}</a>
        </aside>
      </section>

      <nav className="section-nav" aria-label="Secciones de prevención">
        <a href="#prevenir">Prevención</a>
        <a href="#sintomas">Síntomas</a>
        <a href="#centros">Centros de salud</a>
        <a href="#contactos">Teléfonos</a>
        <a href="#reportar">Reporte anónimo</a>
        <a href="#seguimiento">Seguimiento</a>
      </nav>

      <main className="prevention-content">
        <PreventionGuide content={content} />
        <SymptomsAlert content={content} />
        <HealthFacilitiesMap collection={facilities} />

        <section id="contactos" className="info-section contact-section" aria-labelledby="contacts-title">
          <div className="info-section-heading">
            <div>
              <h2 id="contacts-title">Teléfonos útiles</h2>
            </div>
            <p>No se encontró un celular municipal vigente dedicado exclusivamente a descacharreo o fumigación. Las centrales publicadas pueden orientar sobre el canal actual.</p>
          </div>
          <div className="contact-list">
            {content.contacts.map((contact) => (
              <article key={contact.id}>
                <span className={contact.status}>{contact.status.replaceAll('_', ' ')}</span>
                <h3>{contact.label}</h3>
                <p>{contact.purpose}</p>
                <a href={`tel:${contact.number_tel}`}><PhoneIcon className="button-icon" />{contact.number_display}</a>
                <small>
                  Revisado {contact.reviewed_at} ·{' '}
                  <a href={contact.source_url} target="_blank" rel="noreferrer">ver fuente oficial</a>
                </small>
              </article>
            ))}
          </div>
        </section>

        <CitizenReportForm />
        <ReportStatusLookup />

        <section className="source-section" aria-labelledby="source-title">
          <div>
            <h2 id="source-title">Fuentes sanitarias y operativas</h2>
            <p>Contenido revisado el {content.reviewed_at}. Los datos operativos pueden cambiar.</p>
          </div>
          <ul>
            {content.sources.map((source) => (
              <li key={source.url}>
                <a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>
                <span>{source.publisher}</span>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  )
}
