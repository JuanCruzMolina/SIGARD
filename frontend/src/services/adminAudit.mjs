// Auditoría (F6.6): labels, URL state and texts of the read-only audit screen.
// Texts are built only from the fields the API returns for each category (the API itself sends a
// closed list per category); unknown keys are ignored here too. Never free text, values or secrets.
import { REASON_LABELS, formatWeek } from './internalAlerts.mjs'

export const AUDIT_PAGE_SIZE = 25
export const ARGENTINA_TIME_ZONE = 'America/Argentina/Buenos_Aires'
export const LOCAL_ONLY_NOTICE = 'La auditoría se consulta en el entorno local de administración (npm run dev).'
export const PRIVACY_NOTICE = 'Sólo se muestran acciones y metadatos: nunca contraseñas, notas, comentarios, descripciones ni valores del visor.'

export const CATEGORIES = {
  cuentas: 'Cuentas', reportes: 'Reportes', contenido: 'Contenido', alertas: 'Alertas', visor: 'Visor (modo privado)', auditoria: 'Auditoría',
}
export const ACTIONS = {
  cuentas: { created: 'Cuenta creada', password_rotated: 'Contraseña rotada', deactivated: 'Cuenta desactivada' },
  reportes: { view_detail: 'Detalle de reporte consultado', export_csv: 'Reportes exportados (CSV)', update: 'Reporte actualizado' },
  contenido: { seed_import: 'Carga inicial', create: 'Borrador creado', update: 'Borrador editado', publish: 'Versión publicada', unpublish: 'Sección despublicada' },
  alertas: {
    rule_created: 'Regla creada', rule_updated: 'Regla editada', evaluation_run: 'Semana evaluada', evaluation_no_data: 'Evaluación sin datos',
    candidate_approved: 'Candidata aprobada', candidate_discarded: 'Candidata descartada',
    citizen_publication_blocked: 'Publicación ciudadana bloqueada', candidates_exported: 'Candidatas exportadas (CSV)',
  },
  visor: { private_query: 'Consulta con valores exactos' },
  auditoria: { audit_viewed: 'Auditoría consultada' },
}
const FIELDS = {
  reportes: { status: 'estado', public_status_message: 'mensaje público', internal_notes: 'nota interna', possible_duplicate_of: 'posible duplicado' },
  contenido: { title: 'título', body: 'contenido', position: 'orden', source_label: 'fuente', source_url: 'enlace de fuente' },
  alertas: { name: 'nombre', capability: 'pregunta', model: 'modelo', radio_ids: 'radios', threshold: 'umbral', consecutive_weeks: 'semanas consecutivas', enabled: 'activa' },
}
const REPORT_STATUSES = {
  recibido: 'Recibido', en_revision: 'En revisión', pendiente_de_derivacion: 'Pendiente de derivación', derivado: 'Derivado', resuelto: 'Resuelto', descartado: 'Descartado',
}
const FILTER_LABELS = { category: 'categoría', action: 'acción', actor_id: 'usuario', date_from: 'desde', date_to: 'hasta', page: 'página', page_size: 'por página' }
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/

// URL ↔ filters (shareable and kept on reload). Empty values and page 1 stay out of the URL.
export function filtersFromSearch(params) {
  const category = CATEGORIES[params.get('categoria')] ? params.get('categoria') : ''
  const action = category && ACTIONS[category][params.get('accion')] ? params.get('accion') : ''
  const actor = /^[1-9]\d{0,9}$/.test(params.get('usuario') || '') ? params.get('usuario') : ''
  const from = ISO_DAY.test(params.get('desde') || '') ? params.get('desde') : ''
  const to = ISO_DAY.test(params.get('hasta') || '') ? params.get('hasta') : ''
  const page = /^[1-9]\d{0,5}$/.test(params.get('pagina') || '') ? Number(params.get('pagina')) : 1
  return { category, action, actor, from, to, page }
}

export function searchFromFilters(filters) {
  const entries = [['categoria', filters.category], ['accion', filters.category ? filters.action : ''], ['usuario', filters.actor],
    ['desde', filters.from], ['hasta', filters.to], ['pagina', filters.page > 1 ? String(filters.page) : '']]
  return new URLSearchParams(entries.filter(([, value]) => value))
}

export function apiQuery(filters) {
  const entries = [['category', filters.category], ['action', filters.category ? filters.action : ''], ['actor_id', filters.actor],
    ['date_from', filters.from], ['date_to', filters.to], ['page', String(filters.page || 1)], ['page_size', String(AUDIT_PAGE_SIZE)]]
  return new URLSearchParams(entries.filter(([, value]) => value)).toString()
}

const dateTime = new Intl.DateTimeFormat('es-AR', { timeZone: ARGENTINA_TIME_ZONE, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
export function argentinaDateTime(iso) {
  return dateTime.format(new Date(iso))
}

export function actionLabel(event) {
  return ACTIONS[event.category]?.[event.action] || event.action
}

const fieldNames = (category, fields) => (Array.isArray(fields) ? fields : []).map(field => FIELDS[category]?.[field]).filter(Boolean)

// «Objeto» column: what the action was about.
export function objectText(event) {
  const target = event.target || {}
  switch (event.category) {
    case 'cuentas': return target.account_email ? `Cuenta ${target.account_email}` : 'Cuenta'
    case 'reportes': return target.tracking_code ? `Reporte ${target.tracking_code}` : 'Reportes ciudadanos'
    case 'contenido': return target.section_title ? `Sección «${target.section_title}»` : target.section_slug ? `Sección ${target.section_slug}` : 'Sección'
    case 'alertas':
      if (target.rule_name) return `Regla «${target.rule_name}»`
      if (target.radio_id) return `Radio ${target.radio_id}${target.target_week ? ` · semana del ${formatWeek(target.target_week)}` : ''}`
      if (target.target_week) return `Semana del ${formatWeek(target.target_week)}`
      return target.candidate_id ? `Candidata ${target.candidate_id}` : 'Alertas internas'
    case 'visor': return [target.route && `Consulta «${target.route}»`, target.period, target.radio_id && `radio ${target.radio_id}`].filter(Boolean).join(' · ') || 'Visor'
    default: return '—'
  }
}

// «Detalle» column: the safe summary (closed lists only).
export function detailText(event) {
  const summary = event.summary || {}
  const parts = []
  if (REPORT_STATUSES[summary.status_from] && REPORT_STATUSES[summary.status_to]) parts.push(`Estado: ${REPORT_STATUSES[summary.status_from]} → ${REPORT_STATUSES[summary.status_to]}`)
  const changed = fieldNames(event.category, summary.changed_fields)
  if (changed.length) parts.push(`Cambios: ${changed.join(', ')}`)
  if (Number.isInteger(summary.count)) parts.push(`${summary.count} ${event.category === 'alertas' ? (summary.count === 1 ? 'candidata' : 'candidatas') : (summary.count === 1 ? 'reporte' : 'reportes')}`)
  if (Number.isInteger(summary.version)) parts.push(`Versión ${summary.version}`)
  if (Number.isInteger(summary.created)) parts.push(`${summary.created} ${summary.created === 1 ? 'candidata nueva' : 'candidatas nuevas'}`)
  if (REASON_LABELS[summary.reason]) parts.push(`Motivo: ${REASON_LABELS[summary.reason]}`)
  if (typeof summary.has_comment === 'boolean') parts.push(summary.has_comment ? 'Con comentario' : 'Sin comentario')
  if (event.category === 'visor') parts.push('Valores exactos (modo privado)')
  if (summary.filters && typeof summary.filters === 'object') {
    const filters = Object.entries(summary.filters).filter(([key]) => FILTER_LABELS[key]).map(([key, value]) => `${FILTER_LABELS[key]} ${key === 'category' ? CATEGORIES[value] || value : value}`)
    parts.push(filters.length ? `Filtros: ${filters.join(', ')}` : 'Sin filtros')
  }
  return parts.join(' · ')
}
