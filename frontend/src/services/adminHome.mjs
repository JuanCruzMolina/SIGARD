// Administración v2 · Inicio (F5): pure helpers. Every number comes from an existing API response;
// a source that did not answer is shown as «No disponible», never as a number.
import { epiWeekLabel } from './adminShell.mjs'
import { REPORT_CATEGORY_LABELS } from './citizenReportValidation.mjs'

export const NOT_AVAILABLE = 'No disponible'
export const EXPERIMENTAL_LABEL = 'Prototipo experimental — reconstrucción histórica, no uso operativo'
// Oldest pending items listed on Inicio (the sections hold the complete lists).
export const PENDING_LIMIT = 10

// A source is { status: 'loading' | 'ok' | 'error' | 'absent', count?, items? }.
export const loaded = source => source?.status === 'ok' && Number.isInteger(source.count)
export function countText(source) {
  if (source?.status === 'loading') return 'Cargando…'
  return loaded(source) ? String(source.count) : NOT_AVAILABLE
}

// Received reports come newest first (GET /admin/citizen-reports orders by created_at desc). The
// oldest `size` of `total` are on the last page and, when it is short, the one before it.
export function oldestReportPages(total, size = PENDING_LIMIT) {
  if (!Number.isInteger(total) || total <= size) return []
  const last = Math.ceil(total / size)
  return total % size ? [last - 1, last] : [last]
}

const time = iso => { const value = Date.parse(iso || ''); return Number.isNaN(value) ? Infinity : value }

// One list for the three kinds, oldest first (ties: alert, report, content; then id).
export function pendingItems({ alerts, reports, content }) {
  const items = []
  if (alerts?.status === 'ok') for (const candidate of alerts.items) items.push({
    kind: 'alerta', id: `alerta-${candidate.id}`, date: candidate.created_at, href: '/admin/alertas',
    detail: [candidate.rule?.name || 'Regla sin nombre', `Radio ${candidate.radio_id}`, epiWeekLabel(candidate.target_week)].filter(Boolean),
  })
  if (reports?.status === 'ok') for (const report of reports.items) items.push({
    kind: 'reporte', id: `reporte-${report.id}`, date: report.created_at, href: '/admin/reportes',
    detail: [REPORT_CATEGORY_LABELS[report.category] || report.category, `seguimiento ${report.tracking_code}`],
  })
  if (content?.status === 'ok') for (const section of content.items) items.push({
    kind: 'contenido', id: `contenido-${section.id}`, date: section.updated_at, href: '/admin/contenido',
    detail: [`Sección «${section.title}» con cambios sin publicar`],
  })
  const order = { alerta: 0, reporte: 1, contenido: 2 }
  return items.sort((a, b) => time(a.date) - time(b.date) || order[a.kind] - order[b.kind] || a.id.localeCompare(b.id))
}

export function formatReceived(iso) {
  const value = new Date(iso || '')
  return Number.isNaN(value.getTime()) ? NOT_AVAILABLE : value.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// Public map with real data: the public activity API decides (served package → on; 404 → off).
export function publicMapText(activity) {
  if (!activity || activity.status === 'loading') return 'Cargando…'
  if (activity.enabled) return 'Activado · la API pública sirve el paquete autorizado'
  return activity.unavailable ? NOT_AVAILABLE : 'Desactivado · la API pública no lo habilita'
}

// Models in the predictive catalog (all experimental; the contract rejects promoted ones).
export function modelsText(catalog) {
  const candidates = catalog?.experimental_candidates
  if (!Array.isArray(candidates)) return NOT_AVAILABLE
  const notPromoted = candidates.filter(c => c.promotion?.decision === 'not_promoted').length
  return notPromoted === candidates.length
    ? `Experimentales · no promovidos para uso operativo (${candidates.length} candidatos)`
    : NOT_AVAILABLE
}

// Integrity of the viewer package, as the API answered /calendar (it verifies hashes per request).
export function integrityText({ viewer, catalog, error }) {
  if (!viewer) return `${NOT_AVAILABLE} · sin visor predictivo en este entorno`
  if (catalog) return 'Verificada por la API en esta consulta'
  if (error?.status === 503) return 'No verificada · el paquete falta o no pudo verificarse'
  return error ? NOT_AVAILABLE : 'Cargando…'
}
