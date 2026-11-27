import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import RestrictedMarkdown, { SectionSource } from '../components/RestrictedMarkdown'
import { AlertIcon, HealthIcon, HomeIcon, MapIcon, PhoneIcon, PinIcon, ShieldIcon } from '../components/InfoIcons'
import { loadPreventionData } from '../services/preventionData'
import { sectionsBySlug } from '../services/preventionContent.mjs'
import { EXCLUDED_YEAR_TEXT, loadActivity } from '../services/publicActivity.mjs'
import { REPORT_PRIVACY, REPORT_SCOPE } from '../services/citizenReportValidation.mjs'
import { activityState, barWidth, calendarPeaks, CARE_SLUGS, emergencyContact, EMPTY, FICTIONAL_NOTICE, isFictional, longDate, pickSections,
  PREVENTION_SLUGS, publishedContacts, recentWeeks, seasonCalendar, weeklyTrend } from '../services/publicHome.mjs'
import '../PublicHome.css'

// Public home page (Situación actual): prevention, care, citizen report and observed aggregates only.
// Health text, phone numbers and sources come from published content; figures from the authorized
// activity package. No prediction, simulation, radio ranking or model name is shown here.

function Empty({ children, link }) {
  return <div className="home-empty" role="status"><p>{children}</p>{link}</div>
}

function FictionalNotice() {
  return <p className="home-fictional" role="note" data-testid="fictional-notice"><strong>{FICTIONAL_NOTICE}.</strong> No corresponden a registros reales.</p>
}

function DataDate({ activity }) {
  return <p className="home-date" data-testid="data-date"><strong>Datos hasta el {longDate(activity.period.end)}.</strong> Es una reconstrucción histórica: no muestra la situación actual.</p>
}

function Bars({ rows, max, caption }) {
  return <ol className="home-bars" aria-label={caption}>
    {rows.map(row => <li key={row.key} className={row.known ? '' : 'protected'}>
      <span className="bar-label">{row.label}</span>
      <span className="bar-track" aria-hidden="true">{row.known && <span className="bar-fill" style={{ width: `${barWidth(row.value, max)}%` }} />}</span>
      <span className="bar-value">{row.text}</span>
    </li>)}
  </ol>
}

function ProtectionNote({ activity }) {
  return <div className="home-notes">
    <p>Un registro no siempre es un caso confirmado. Las cifras menores a 5 se muestran como «Menos de 5» para proteger la identidad de las personas.</p>
    <p>{EXCLUDED_YEAR_TEXT}</p>
    <p>Fuente: {activity.source?.label || 'paquete de actividad autorizado'}.</p>
  </div>
}

export function Situation({ activity }) {
  if (activity.status === 'loading') return <Empty>Cargando el resumen de registros…</Empty>
  if (activity.status !== 'ready') return <Empty>{activity.status === 'unavailable' ? EMPTY.activityUnavailable : EMPTY.activityDisabled}</Empty>
  const data = activity.activity
  const weeks = recentWeeks(data)
  const trend = weeklyTrend(weeks)
  const max = Math.max(0, ...weeks.map(week => (Number.isInteger(week.value) ? week.value : 0)))
  return <>
    {isFictional(data) && <FictionalNotice />}
    <DataDate activity={data} />
    <div className={`home-trend ${trend.kind}`} data-testid="trend">{trend.title && <strong>{trend.title}</strong>}<p>{trend.text}</p></div>
    <h3>Las últimas {weeks.length} semanas con datos</h3>
    <Bars caption="Registros por semana en la ciudad" max={max} rows={weeks.map(week => ({ key: week.start, ...week }))} />
    <ProtectionNote activity={data} />
  </>
}

export function Calendar({ activity }) {
  const [chosen, setChosen] = useState(null)
  if (activity.status === 'loading') return <Empty>Cargando el calendario…</Empty>
  if (activity.status !== 'ready') return <Empty>{activity.status === 'unavailable' ? EMPTY.activityUnavailable : EMPTY.calendarDisabled}</Empty>
  const data = activity.activity
  const calendar = seasonCalendar(data)
  const year = calendar.years.find(item => item.year === chosen) || calendar.years.at(-1)
  const peaks = calendarPeaks(calendar)
  return <>
    {isFictional(data) && <FictionalNotice />}
    <DataDate activity={data} />
    {peaks && <p className="home-peaks" data-testid="peaks">{peaks}</p>}
    <div className="home-years" role="group" aria-label="Elegí un año">
      {calendar.years.map(item => <button key={item.year} type="button" aria-pressed={item.year === year.year} onClick={() => setChosen(item.year)}>{item.year}</button>)}
    </div>
    <h3>Registros cada 4 semanas en {year.year}</h3>
    <Bars caption={`Registros cada 4 semanas en ${year.year}`} max={calendar.max}
      rows={year.periods.map(period => ({ key: period.id, label: period.label, value: period.total, known: period.total !== null, text: period.text }))} />
    <p className="home-scale">Todas las barras usan la misma escala, para comparar entre años.</p>
  </>
}

function PublishedSections({ prevention, slugs, className = '' }) {
  if (prevention.status === 'loading') return <Empty>Cargando contenido…</Empty>
  if (prevention.status !== 'ready') return <Empty link={<Link to="/prevencion">Ir a Prevención y ayuda</Link>}>{EMPTY.contentError}</Empty>
  const sections = pickSections(sectionsBySlug(prevention.data.sections), slugs)
  if (!sections.length) return <Empty link={<Link to="/prevencion">Ir a Prevención y ayuda</Link>}>{EMPTY.content}</Empty>
  return <div className={`home-cards ${className}`}>
    {sections.map(section => <article key={section.slug} data-slug={section.slug} className={section.slug === 'signos-alarma' ? 'alarm' : undefined}>
      {section.slug === 'signos-alarma' && <AlertIcon className="home-icon" />}
      <h3>{section.title}</h3>
      <RestrictedMarkdown text={section.body} />
      <SectionSource section={section} />
    </article>)}
  </div>
}

function EmergencyCall({ prevention }) {
  const contact = prevention.status === 'ready' ? emergencyContact(prevention.data.content) : null
  if (!contact) return null
  return <a className="home-call" data-testid="emergency-call" href={`tel:${contact.number_tel}`}><PhoneIcon className="home-icon" />{contact.label}: {contact.number_display}</a>
}

function Contacts({ prevention }) {
  if (prevention.status !== 'ready') return <Empty>{prevention.status === 'loading' ? 'Cargando teléfonos…' : EMPTY.contentError}</Empty>
  const { content } = prevention.data
  const contacts = publishedContacts(content)
  return <>
    {contacts.length ? <ul className="home-contacts">
      {contacts.map(contact => <li key={contact.id}>
        <strong>{contact.label}</strong>
        <span>{contact.purpose}</span>
        <a href={`tel:${contact.number_tel}`}><PhoneIcon className="home-icon" />{contact.number_display}</a>
        <small>Revisado el {longDate(contact.reviewed_at)} · <a href={contact.source_url} target="_blank" rel="noreferrer noopener">ver fuente</a></small>
      </li>)}
    </ul> : <Empty>{EMPTY.contacts}</Empty>}
    {content.sources?.length > 0 && <>
      <h3>Fuentes oficiales</h3>
      <ul className="home-sources">{content.sources.map(source => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer noopener">{source.title}</a> · {source.publisher}</li>)}</ul>
    </>}
  </>
}

export function HomeView({ prevention, activity }) {
  return <div className="content-wrap public-home">
    <header className="page-intro home-intro">
      <h1>Dengue en La Rioja Capital</h1>
      <p>Cómo prevenirlo, qué síntomas observar, cómo avisar sobre un posible criadero y cómo fueron los registros en años anteriores.</p>
      <nav className="home-actions" aria-label="Accesos principales">
        <Link to="/prevencion#prevenir"><HomeIcon className="home-icon" />Cómo prevenir</Link>
        <Link to="/prevencion#reportar"><PinIcon className="home-icon" />Reportar un posible criadero</Link>
        <Link to="/mapa"><MapIcon className="home-icon" />Ver el mapa</Link>
      </nav>
    </header>

    <section className="home-section" id="situacion" aria-labelledby="home-situation-title">
      <h2 id="home-situation-title">Registros de dengue en la ciudad</h2>
      <Situation activity={activity} />
    </section>

    <section className="home-section" id="hoy" aria-labelledby="home-today-title">
      <h2 id="home-today-title">Qué podés hacer hoy</h2>
      <PublishedSections prevention={prevention} slugs={PREVENTION_SLUGS} />
      <Link className="home-more" to="/prevencion#prevenir">Ver toda la guía de prevención</Link>
    </section>

    <section className="home-section" id="sintomas" aria-labelledby="home-care-title">
      <h2 id="home-care-title">Síntomas y cuándo consultar</h2>
      <PublishedSections prevention={prevention} slugs={CARE_SLUGS} className="care" />
      <div className="home-links"><EmergencyCall prevention={prevention} /><Link className="home-more" to="/prevencion#centros"><HealthIcon className="home-icon" />Buscar un centro de salud</Link></div>
    </section>

    <section className="home-section" id="reporte" aria-labelledby="home-report-title">
      <h2 id="home-report-title">Cómo funciona el reporte ciudadano</h2>
      <p>Podés avisar sobre agua acumulada, chatarra, microbasurales u otros lugares donde se puede criar el mosquito.</p>
      <ol className="home-steps">
        <li><strong>Contá qué viste.</strong> Elegí una categoría y describilo en pocas palabras, sin datos personales.</li>
        <li><strong>Marcá el lugar.</strong> Indicá en el mapa la ubicación aproximada.</li>
        <li><strong>Guardá tu código.</strong> Con el código de seguimiento podés consultar cómo avanza tu reporte.</li>
      </ol>
      <div className="home-privacy"><ShieldIcon className="home-icon" /><p><strong>{REPORT_PRIVACY.lead}</strong> {REPORT_PRIVACY.body}</p></div>
      <p className="home-muted">{REPORT_SCOPE}</p>
      <div className="home-links"><Link className="home-button" to="/prevencion#reportar">Hacer un reporte</Link><Link className="home-more" to="/prevencion#seguimiento">Consultar un reporte</Link></div>
    </section>

    <section className="home-section" id="calendario" aria-labelledby="home-calendar-title">
      <h2 id="home-calendar-title">Calendario de temporada</h2>
      <p>Cómo se distribuyeron los registros a lo largo del año en años anteriores.</p>
      <Calendar activity={activity} />
    </section>

    <section className="home-section" id="sobre" aria-labelledby="home-about-title">
      <h2 id="home-about-title">Sobre SIGARD</h2>
      <p>SIGARD es un prototipo académico para la vigilancia territorial del dengue en La Rioja Capital. No es un servicio oficial del Municipio ni del Ministerio de Salud, y no reemplaza la consulta médica.</p>
      <p>Privacidad: los registros se muestran sumados para toda la ciudad, nunca por persona ni por domicilio. Los reportes ciudadanos son anónimos y su ubicación no se publica.</p>
      <h3>Teléfonos y canales oficiales</h3>
      <Contacts prevention={prevention} />
    </section>
  </div>
}

export default function Dashboard() {
  const [prevention, setPrevention] = useState({ status: 'loading' })
  const [activity, setActivity] = useState({ status: 'loading' })
  useEffect(() => {
    let live = true
    loadPreventionData().then(data => { if (live) setPrevention({ status: 'ready', data }) }, () => { if (live) setPrevention({ status: 'error' }) })
    loadActivity().then(result => { if (live) setActivity(activityState(result)) })
    return () => { live = false }
  }, [])
  return <HomeView prevention={prevention} activity={activity} />
}
