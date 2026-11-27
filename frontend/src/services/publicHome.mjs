// Pure helpers of the public home page (Situación actual). Shared by the page and node tests.
// Rules: only observed aggregates from the authorized activity package (values below 5 arrive
// as "<5"/"oculto" and are never turned into numbers); health text, phone numbers and sources
// come from published content, never from this module.
import { blockItemTexts, CONTENT_PENDING, parseRestrictedMarkdown } from './preventionContent.mjs'

export const PUBLISHED_CONTACT_STATUSES = new Set(['publicado', 'confirmado'])
// Contacts highlighted with a call button: only those marked as emergency in the content itself.
export const EMERGENCY_CATEGORY = 'emergencia'
export const PREVENTION_SLUGS = ['prevencion', 'control-vectorial']
export const CARE_SLUGS = ['sintomas', 'consejos-medicos', 'signos-alarma']
export const ALARM_SLUG = 'signos-alarma'
// Home preview: the first items of each published section; the alarm signs are never shortened.
export const PREVIEW_ITEMS = 3
export const RECENT_WEEKS = 8
export const FICTIONAL_NOTICE = 'Datos ficticios de demostración'

export const EMPTY = {
  activityDisabled: 'Los datos de registros todavía no están autorizados para publicarse. Cuando el Ministerio de Salud de La Rioja lo autorice, vas a ver acá el resumen semanal.',
  activityUnavailable: 'El resumen de registros no está disponible por el momento. Intentá nuevamente más tarde.',
  content: CONTENT_PENDING,
  contentError: 'No pudimos cargar el contenido preventivo. Intentá nuevamente más tarde.',
  contacts: 'Todavía no hay teléfonos confirmados para mostrar. Consultá las fuentes oficiales.',
}

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
const DAY_MS = 86400000

function parts(iso) {
  const [year, month, day] = String(iso).split('-').map(Number)
  return { year, month, day }
}
const time = iso => { const { year, month, day } = parts(iso); return Date.UTC(year, month - 1, day) }

export function longDate(iso, withYear = true) {
  const { year, month, day } = parts(iso)
  return `${day} de ${MONTHS[month - 1]}${withYear ? ` de ${year}` : ''}`
}

// "del 2 al 8 de junio de 2024", "del 26 de mayo al 1 de junio" (withYear false), across years always both.
export function rangeLabel(start, end, { withYear = true } = {}) {
  const a = parts(start), b = parts(end)
  if (a.year !== b.year) return `del ${longDate(start)} al ${longDate(end)}`
  const tail = withYear ? ` de ${b.year}` : ''
  if (a.month === b.month) return `del ${a.day} al ${b.day} de ${MONTHS[b.month - 1]}${tail}`
  return `del ${longDate(start, false)} al ${longDate(end, false)}${tail}`
}

export function isFictional(activity) {
  return activity?.source?.fictional === true || activity?.source?.kind === 'fixture'
}

// loadActivity() result → page state. 404 = not authorized; anything else failing = unavailable.
export function activityState(result) {
  if (result?.enabled && result.activity) return { status: 'ready', activity: result.activity }
  return { status: result?.unavailable ? 'unavailable' : 'disabled' }
}

// Display of one aggregated value; protected values keep their protected label.
export function valueDisplay(value, display) {
  if (Number.isInteger(value)) return { known: true, text: `${value} ${value === 1 ? 'registro' : 'registros'}` }
  if (display === 'oculto') return { known: false, text: 'Dato protegido' }
  return { known: false, text: 'Menos de 5' }
}

export function cityWeeks(activity) {
  return (activity?.blocks || []).flatMap(block => block.city_weeks || []).slice().sort((a, b) => time(a.start) - time(b.start))
}

export function recentWeeks(activity, count = RECENT_WEEKS) {
  return cityWeeks(activity).slice(-count).map(week => ({ ...week, label: rangeLabel(week.start, week.end), ...valueDisplay(week.value, week.display) }))
}

const consecutive = weeks => weeks.every((week, index) => index === 0 || time(week.start) - time(weeks[index - 1].start) === 7 * DAY_MS)
const plural = n => `${n} ${n === 1 ? 'registro' : 'registros'}`

// Last 4 weeks against the previous 4, only when all 8 are consecutive and visible.
export function weeklyTrend(weeks) {
  if (weeks.length < RECENT_WEEKS || !consecutive(weeks)) return { kind: 'unavailable', text: 'No hay 8 semanas seguidas con datos para comparar.' }
  if (!weeks.every(week => Number.isInteger(week.value))) {
    return { kind: 'unavailable', text: 'No se puede calcular si los registros subieron o bajaron sin revelar valores protegidos (semanas con menos de 5 registros).' }
  }
  const half = RECENT_WEEKS / 2
  const previous = weeks.slice(0, half).reduce((sum, week) => sum + week.value, 0)
  const recent = weeks.slice(half).reduce((sum, week) => sum + week.value, 0)
  const detail = `${plural(recent)} en las últimas 4 semanas, frente a ${plural(previous)} en las 4 anteriores.`
  if (recent >= previous * 1.2) return { kind: 'up', title: 'Los registros aumentaron', text: detail, recent, previous }
  if (recent <= previous * 0.8) return { kind: 'down', title: 'Los registros disminuyeron', text: detail, recent, previous }
  return { kind: 'flat', title: 'Los registros se mantuvieron parecidos', text: detail, recent, previous }
}

// Four-week periods per year. A period total exists only when every week of it is visible.
export function seasonCalendar(activity) {
  const years = new Map()
  for (const block of activity?.blocks || []) {
    const weeks = block.city_weeks || []
    const known = weeks.length > 0 && weeks.every(week => Number.isInteger(week.value))
    const total = known ? weeks.reduce((sum, week) => sum + week.value, 0) : null
    const hidden = weeks.some(week => week.display === 'oculto')
    const period = { id: block.id, start: block.start, end: block.end, label: rangeLabel(block.start, block.end, { withYear: false }), total,
      text: known ? plural(total) : hidden ? 'Dato protegido' : 'Incluye semanas con menos de 5' }
    if (!years.has(block.year)) years.set(block.year, [])
    years.get(block.year).push(period)
  }
  const list = [...years].sort(([a], [b]) => a - b).map(([year, periods]) => ({ year, periods }))
  const max = Math.max(0, ...list.flatMap(year => year.periods.map(period => period.total ?? 0)))
  return { years: list, max }
}

// Sentence built only from the data: the periods with the most visible registrations.
export function calendarPeaks(calendar, count = 3) {
  const ranked = calendar.years.flatMap(({ year, periods }) => periods.filter(p => p.total !== null).map(p => ({ ...p, year })))
    .sort((a, b) => b.total - a.total || time(a.start) - time(b.start)).slice(0, count)
  if (!ranked.length) return ''
  return `Los períodos con más registros fueron: ${ranked.map(p => `${rangeLabel(p.start, p.end)} (${plural(p.total)})`).join('; ')}.`
}

export const barWidth = (value, max) => (Number.isInteger(value) && max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0)

export function publishedContacts(content) {
  return (content?.contacts || []).filter(contact => PUBLISHED_CONTACT_STATUSES.has(contact.status) && contact.number_tel && contact.number_display)
}

// The emergency number follows the contacts rule: shown only when its contact is published.
export function emergencyContact(content) {
  if (!content?.emergency_number) return null
  return publishedContacts(content).find(contact => contact.number_tel === content.emergency_number) || null
}

export function pickSections(bySlug, slugs) {
  return slugs.map(slug => bySlug?.[slug]).filter(Boolean)
}

export const previewLimit = section => (section?.slug === ALARM_SLUG ? undefined : PREVIEW_ITEMS)

// One line for the alarm strip, built only from the published section: its title and every item, verbatim.
export function alarmLine(section) {
  const items = section ? blockItemTexts(parseRestrictedMarkdown(section.body)) : []
  if (!items.length) return null
  return { title: section.title, text: items.join(' ') }
}

// Contacts marked as emergency in the content are highlighted with a call button; the remaining
// published contacts are grouped by name in a compact list. Same publication rule for both.
export function contactGroups(content) {
  const contacts = publishedContacts(content)
  const urgent = contact => contact.category === EMERGENCY_CATEGORY
  const groups = new Map()
  for (const contact of contacts.filter(contact => !urgent(contact))) {
    if (!groups.has(contact.label)) groups.set(contact.label, { label: contact.label, purpose: contact.purpose, contacts: [], sources: [] })
    const group = groups.get(contact.label)
    group.contacts.push(contact)
    if (contact.source_url && !group.sources.includes(contact.source_url)) group.sources.push(contact.source_url)
  }
  return { urgent: contacts.filter(urgent), groups: [...groups.values()], reviewed: reviewedLabel(contacts) }
}

export function reviewedLabel(contacts) {
  const dates = [...new Set(contacts.map(contact => contact.reviewed_at).filter(Boolean))].sort()
  if (!dates.length) return ''
  if (dates.length === 1) return `Revisado el ${longDate(dates[0])}.`
  return `Revisado entre el ${longDate(dates[0])} y el ${longDate(dates.at(-1))}.`
}
