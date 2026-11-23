// Administración v2 (F4): sections of the side menu and the small pure helpers of the frame.
// No data is written here; the frame only reads the session claims, the email kept at login and
// the public weeks manifest (/data/available_weeks.json).

export const ADMIN_HOME = '/admin/inicio'

// Icon paths follow docs/diseno/admin-v2 (24×24, stroke). `when` hides a section in a mode.
export const ADMIN_SECTIONS = [
  { key: 'inicio', group: 'operacion', label: 'Inicio', path: '/admin/inicio', icon: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z' },
  { key: 'predictivo', group: 'operacion', label: 'Módulo predictivo', path: '/admin/predictivo', icon: 'M9 4L3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14', when: mode => mode.localResearch },
  { key: 'alertas', group: 'operacion', label: 'Alertas internas', path: '/admin/alertas', icon: 'M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0', when: mode => !mode.demo },
  { key: 'reportes', group: 'operacion', label: 'Reportes ciudadanos', path: '/admin/reportes', icon: 'M4 4h16v12H5.2L4 17.2zM8 9h8M8 12h5' },
  { key: 'contenido', group: 'gestion', label: 'Contenido preventivo', path: '/admin/contenido', icon: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z' },
  { key: 'cuentas', group: 'gestion', label: 'Cuentas', path: '/admin/cuentas', icon: 'M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21c0-4 3-6 7-6s7 2 7 6M17 11h5M19.5 8.5v5' },
  { key: 'auditoria', group: 'gestion', label: 'Auditoría', path: '/admin/auditoria', icon: 'M9 4h6l1 3h4v13H4V7h4zM8 13l3 3 5-5' },
]
export const ADMIN_GROUPS = [{ key: 'operacion', label: 'Operación' }, { key: 'gestion', label: 'Gestión' }]

export function visibleSections(mode) {
  return ADMIN_SECTIONS.filter(section => !section.when || section.when(mode))
}

export function sectionForPath(pathname) {
  return ADMIN_SECTIONS.find(section => pathname === section.path || pathname.startsWith(`${section.path}/`)) || null
}

// Epidemiological week (Sunday–Saturday; week 1 is the one holding 4 January, so some years
// have week 53), the calendar of the predictive module. `iso` is a YYYY-MM-DD date.
export function epiWeekOf(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '')
  if (!match) return null
  const day = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  const weekOneStart = year => { const jan4 = Date.UTC(year, 0, 4); return jan4 - new Date(jan4).getUTCDay() * 86400000 }
  let year = Number(match[1]) + 1
  while (weekOneStart(year) > day) year -= 1
  return { year, week: Math.floor((day - weekOneStart(year)) / (7 * 86400000)) + 1 }
}

export function epiWeekLabel(iso) {
  const value = epiWeekOf(iso)
  return value ? `SE ${value.week}/${value.year}` : ''
}

// Whole minutes left (rounded up, so "vence en 1 min" until it really expires).
export function minutesLeft(ms) {
  return ms > 0 ? Math.ceil(ms / 60000) : 0
}

export function environmentLabel({ demo, localResearch, dev }) {
  if (demo) return 'Demo ficticia'
  if (localResearch) return 'Local'
  return dev ? 'Desarrollo' : 'Producción'
}
