import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import RestrictedMarkdown, { SectionSource } from '../components/RestrictedMarkdown'
import { AlertIcon, ChartIcon, HealthIcon, HomeIcon, InfoIcon, MapIcon, PhoneIcon, PinIcon, ShieldIcon } from '../components/InfoIcons'
import { loadPreventionData } from '../services/preventionData'
import { sectionsBySlug } from '../services/preventionContent.mjs'
import { EXCLUDED_YEAR_TEXT, loadActivity } from '../services/publicActivity.mjs'
import { REPORT_PRIVACY, REPORT_SCOPE } from '../services/citizenReportValidation.mjs'
import { activityState, ALARM_SLUG, alarmLine, barWidth, calendarPeaks, CARE_SLUGS, contactGroups, emergencyContact, EMPTY, FICTIONAL_NOTICE,
  isFictional, longDate, pickSections, PREVENTION_SLUGS, previewLimit, recentWeeks, seasonCalendar, weeklyTrend } from '../services/publicHome.mjs'
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

function RecentWeeks({ data }) {
  const weeks = recentWeeks(data)
  const trend = weeklyTrend(weeks)
  const max = Math.max(0, ...weeks.map(week => (Number.isInteger(week.value) ? week.value : 0)))
  return <div id="situacion" className="home-subblock">
    <h3>Las últimas {weeks.length} semanas con datos</h3>
    <div className={`home-trend ${trend.kind}`} data-testid="trend">{trend.title && <strong>{trend.title}</strong>}<p>{trend.text}</p></div>
    <Bars caption="Registros por semana en la ciudad" max={max} rows={weeks.map(week => ({ key: week.start, ...week }))} />
  </div>
}

function Calendar({ data }) {
  const [chosen, setChosen] = useState(null)
  const calendar = seasonCalendar(data)
  const year = calendar.years.find(item => item.year === chosen) || calendar.years.at(-1)
  if (!year) return null
  const peaks = calendarPeaks(calendar)
  return <div id="calendario" className="home-subblock">
    <h3>Calendario de temporada</h3>
    <p>Cómo se distribuyeron los registros a lo largo del año en años anteriores.</p>
    {peaks && <p className="home-peaks" data-testid="peaks">{peaks}</p>}
    <div className="home-years" role="group" aria-label="Elegí un año">
      {calendar.years.map(item => <button key={item.year} type="button" aria-pressed={item.year === year.year} onClick={() => setChosen(item.year)}>{item.year}</button>)}
    </div>
    <h4 data-testid="calendar-year">Registros cada 4 semanas en {year.year}</h4>
    <Bars caption={`Registros cada 4 semanas en ${year.year}`} max={calendar.max}
      rows={year.periods.map(period => ({ key: period.id, label: period.label, value: period.total, known: period.total !== null, text: period.text }))} />
    <p className="home-scale">Todas las barras usan la misma escala, para comparar entre años.</p>
  </div>
}

// Registros and Calendario in one block. Without an authorized package: one compact message.
export function CityData({ activity }) {
  if (activity.status === 'loading') return <Empty>Cargando los datos de la ciudad…</Empty>
  if (activity.status !== 'ready') return <Empty>{activity.status === 'unavailable' ? EMPTY.activityUnavailable : EMPTY.activityDisabled}</Empty>
  const data = activity.activity
  return <>
    {isFictional(data) && <FictionalNotice />}
    <DataDate activity={data} />
    <RecentWeeks data={data} />
    <Calendar data={data} />
    <ProtectionNote activity={data} />
  </>
}

function PublishedSections({ prevention, slugs, className = '' }) {
  if (prevention.status === 'loading') return <Empty>Cargando contenido…</Empty>
  if (prevention.status !== 'ready') return <Empty link={<Link to="/prevencion">Ir a Prevención y ayuda</Link>}>{EMPTY.contentError}</Empty>
  const sections = pickSections(sectionsBySlug(prevention.data.sections), slugs)
  if (!sections.length) return <Empty link={<Link to="/prevencion">Ir a Prevención y ayuda</Link>}>{EMPTY.content}</Empty>
  return <div className={`home-cards ${className}`}>
    {sections.map(section => <article key={section.slug} data-slug={section.slug} className={section.slug === ALARM_SLUG ? 'alarm' : undefined}>
      <h3>{section.slug === ALARM_SLUG && <AlertIcon className="home-icon" />}{section.title}</h3>
      <RestrictedMarkdown text={section.body} limit={previewLimit(section)} />
      <SectionSource section={section} />
    </article>)}
  </div>
}

function EmergencyCall({ prevention, testId = 'emergency-call' }) {
  const contact = prevention.status === 'ready' ? emergencyContact(prevention.data.content) : null
  if (!contact) return null
  return <a className="home-call" data-testid={testId} href={`tel:${contact.number_tel}`}><PhoneIcon className="home-icon" />{contact.label}: {contact.number_display}</a>
}

// Alarm strip under the accesses: the published alarm signs in one line and the published emergency
// number. Without a confirmed number, a link to the symptoms block instead.
function AlarmStrip({ prevention }) {
  if (prevention.status !== 'ready') return null
  const line = alarmLine(sectionsBySlug(prevention.data.sections)[ALARM_SLUG])
  const hasCall = Boolean(emergencyContact(prevention.data.content))
  if (!line && !hasCall) return null
  return <aside className="home-alarm" data-testid="alarm-strip" aria-label="Signos de alarma">
    {line && <p><AlertIcon className="home-icon" /><span><strong>{line.title}:</strong> {line.text}</span></p>}
    {hasCall ? <EmergencyCall prevention={prevention} testId="alarm-call" /> : <a className="home-alarm-link" data-testid="alarm-link" href="#sintomas">Ver síntomas y signos de alarma</a>}
  </aside>
}

function SectionTitle({ id, icon: Icon, children }) {
  return <h2 id={id}><Icon className="home-icon home-title-icon" />{children}</h2>
}

function Contacts({ prevention }) {
  if (prevention.status !== 'ready') return <Empty>{prevention.status === 'loading' ? 'Cargando teléfonos…' : EMPTY.contentError}</Empty>
  const { content } = prevention.data
  const { urgent, groups, reviewed } = contactGroups(content)
  return <>
    {urgent.length + groups.length === 0 && <Empty>{EMPTY.contacts}</Empty>}
    {urgent.length > 0 && <ul className="home-urgent" data-testid="urgent-contacts">
      {urgent.map(contact => <li key={contact.id}>
        <strong>{contact.label}</strong>
        <span>{contact.purpose}</span>
        <a className="home-call" href={`tel:${contact.number_tel}`}><PhoneIcon className="home-icon" />Llamar al {contact.number_display}</a>
        <a className="home-source" href={contact.source_url} target="_blank" rel="noreferrer noopener">ver fuente</a>
      </li>)}
    </ul>}
    {groups.length > 0 && <ul className="home-contacts" data-testid="contact-list">
      {groups.map(group => <li key={group.label}>
        <strong>{group.label}</strong>
        <span>{group.purpose}</span>
        <span className="home-numbers">{group.contacts.map(contact => <a key={contact.id} href={`tel:${contact.number_tel}`}><PhoneIcon className="home-icon" />{contact.number_display}</a>)}</span>
        {group.sources.map(url => <a key={url} className="home-source" href={url} target="_blank" rel="noreferrer noopener">ver fuente</a>)}
      </li>)}
    </ul>}
    {reviewed && <p className="home-reviewed" data-testid="contacts-reviewed">{reviewed}</p>}
    {content.sources?.length > 0 && <details className="home-sources">
      <summary>Fuentes oficiales ({content.sources.length})</summary>
      <ul>{content.sources.map(source => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer noopener">{source.title}</a> · {source.publisher}</li>)}</ul>
    </details>}
  </>
}

export function HomeView({ prevention, activity }) {
  const withData = activity.status === 'ready'
  return <div className="content-wrap public-home">
    <header className="page-intro home-intro">
      <h1>Dengue en La Rioja Capital</h1>
      <p data-testid="home-subtitle">{withData
        ? 'Cómo prevenirlo, qué síntomas observar, cómo avisar sobre un posible criadero y cómo fueron los registros en años anteriores.'
        : 'Cómo prevenirlo, qué síntomas observar y cómo avisar sobre un posible criadero.'}</p>
      <nav className="home-actions" aria-label="Accesos principales">
        <Link to="/prevencion#prevenir"><HomeIcon className="home-icon" />Cómo prevenir</Link>
        <Link to="/prevencion#reportar"><PinIcon className="home-icon" />Reportar un posible criadero</Link>
        <Link to="/mapa"><MapIcon className="home-icon" />Ver el mapa</Link>
      </nav>
    </header>

    <AlarmStrip prevention={prevention} />

    <section className="home-section" id="hoy" aria-labelledby="home-today-title">
      <SectionTitle id="home-today-title" icon={HomeIcon}>Qué podés hacer hoy</SectionTitle>
      <PublishedSections prevention={prevention} slugs={PREVENTION_SLUGS} />
      <Link className="home-more" data-testid="see-all" to="/prevencion#prevenir" aria-describedby="home-today-title">Ver todo</Link>
    </section>

    <section className="home-section alt" id="sintomas" aria-labelledby="home-care-title">
      <SectionTitle id="home-care-title" icon={HealthIcon}>Síntomas y cuándo consultar</SectionTitle>
      <PublishedSections prevention={prevention} slugs={CARE_SLUGS} className="care" />
      <div className="home-links">
        <EmergencyCall prevention={prevention} />
        <Link className="home-more" data-testid="see-all" to="/prevencion#sintomas" aria-describedby="home-care-title">Ver todo</Link>
        <Link className="home-more" to="/prevencion#centros"><HealthIcon className="home-icon" />Buscar un centro de salud</Link>
      </div>
    </section>

    <section className="home-section" id="reporte" aria-labelledby="home-report-title">
      <SectionTitle id="home-report-title" icon={PinIcon}>Cómo funciona el reporte ciudadano</SectionTitle>
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

    <section className={`home-section alt${withData ? '' : ' compact'}`} id="datos" aria-labelledby="home-data-title">
      <SectionTitle id="home-data-title" icon={ChartIcon}>Datos de la ciudad</SectionTitle>
      <CityData activity={activity} />
    </section>

    <section className="home-section" id="contactos" aria-labelledby="home-contacts-title">
      <SectionTitle id="home-contacts-title" icon={PhoneIcon}>Teléfonos y canales oficiales</SectionTitle>
      <Contacts prevention={prevention} />
    </section>

    <section className="home-section alt" id="sobre" aria-labelledby="home-about-title">
      <SectionTitle id="home-about-title" icon={InfoIcon}>Sobre SIGARD</SectionTitle>
      <p>SIGARD es un prototipo académico para la vigilancia territorial del dengue en La Rioja Capital. No es un servicio oficial del Municipio ni del Ministerio de Salud, y no reemplaza la consulta médica.</p>
      <p>Privacidad: los registros se muestran sumados para toda la ciudad, nunca por persona ni por domicilio. Los reportes ciudadanos son anónimos y su ubicación no se publica.</p>
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
