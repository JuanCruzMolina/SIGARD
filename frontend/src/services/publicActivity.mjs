// Public activity view: protected levels by census radio in fixed 4-week blocks.
// The API answers 404 unless a private authorization binds the package (or the fictional
// fixture is enabled locally). Nothing of the package is ever bundled or stored in /public.
import { fetchRead } from './readRetry.mjs'

export const SCHEMA = 'sigard-public-activity/1'
export const PROTECTED = 'protegido'

// One hue, light to dark: magnitude only. Protected carries a hatch and its own label.
export const LEVELS = [
  { key: 'alto', label: 'Alto', range: '20 o más registros', color: '#0b4f4b' },
  { key: 'medio', label: 'Medio', range: '10 a 19 registros', color: '#3a8f86' },
  { key: 'bajo', label: 'Bajo', range: '5 a 9 registros', color: '#a9d6cd' },
  { key: PROTECTED, label: 'Menos de 5 registros (protegido)', range: 'incluye cero; algunas zonas con más registros también se ocultan para impedir deducciones' },
]
export const LEVEL_KEYS = new Set(LEVELS.map(level => level.key))
export const EXCLUDED_YEAR_TEXT = '2022 no se incluye: ese año los registros tienen una clasificación distinta (se contaron también casos sospechosos, probables y descartados), por lo que no son comparables con los demás años.'

const API_URL = ((import.meta.env && import.meta.env.VITE_API_URL) || 'http://localhost:8000').replace(/\/$/, '')

function fail(reason) { throw new Error(`Paquete de actividad inválido: ${reason}`) }
const isoDate = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)

export function validateActivity(body) {
  if (!body || body.schema !== SCHEMA) fail('schema')
  const { period, blocks } = body
  if (!period || !isoDate(period.start) || !isoDate(period.end) || !period.first_block || !period.last_block) fail('period')
  if (!Array.isArray(blocks) || !blocks.length) fail('blocks')
  if (!isoDate(body.generated_at)) fail('generated_at')
  if (!['territorial_context', 'inline'].includes(body.geometry_source)) fail('geometry_source')
  if (body.geometry_source === 'inline' && body.source?.fictional !== true) fail('inline_geometry_only_for_fixture')
  const seen = new Set()
  for (const block of blocks) {
    if (block.year === 2022) fail('excluded_year')
    if (!isoDate(block.start) || !isoDate(block.end) || !Array.isArray(block.weeks) || !block.weeks.length) fail('block_range')
    for (const week of block.weeks) { const key = `${block.year}-${week}`; if (seen.has(key)) fail('overlap'); seen.add(key) }
    for (const level of Object.values(block.radios || {})) if (!LEVEL_KEYS.has(level)) fail('level')
    for (const entry of block.city_weeks || []) {
      if (entry.value === null ? !['<5', 'oculto'].includes(entry.display) : !(Number.isInteger(entry.value) && entry.value >= 5)) fail('city_week')
    }
  }
  if (blocks[0].id !== period.first_block || blocks.at(-1).id !== period.last_block) fail('period_blocks')
  return body
}

export function formatDay(iso) {
  const [year, month, day] = iso.split('-')
  return `${day}/${month}/${year}`
}

export function blockLabel(block) {
  return `SE ${block.weeks[0]}–${block.weeks.at(-1)}/${block.year}`
}

export function blockRange(block) {
  return `${formatDay(block.start)} al ${formatDay(block.end)}`
}

export function periodBanner(activity) {
  const first = activity.blocks[0], last = activity.blocks.at(-1)
  return `Datos históricos: período ${blockLabel(first)} a ${blockLabel(last)}. No reflejan la situación actual.`
}

export function periodText(activity) {
  const years = [...new Set(activity.blocks.map(b => b.year))].join(', ')
  return `Período cubierto: ${formatDay(activity.period.start)} al ${formatDay(activity.period.end)} (años ${years}).`
}

export function levelCounts(block, radioIds) {
  const counts = Object.fromEntries(LEVELS.map(level => [level.key, 0]))
  for (const id of radioIds) { const level = block.radios[id]; if (level) counts[level] += 1 }
  return counts
}

let pending = null
export const PROBE_TIMEOUT_MS = 5000
// One request per page load; {enabled:false} for 404, network failure, an invalid package or a
// slow API. The probe runs on every page, so it must never stay pending: a busy API (for example
// while a local service preloads) would otherwise keep the page loading indefinitely.
export function loadActivity(fetcher = fetch, timeoutMs = PROBE_TIMEOUT_MS) {
  pending ??= (async () => {
    try {
      // One retry on a network failure or 5xx (404 = disabled is never retried), within the same time limit.
      const response = await fetchRead(`${API_URL}/api/v1/public/activity`, { credentials: 'omit', cache: 'no-store', signal: AbortSignal.timeout(timeoutMs) }, { fetcher })
      if (!response.ok) return { enabled: false }
      return { enabled: true, activity: validateActivity(await response.json()) }
    } catch {
      return { enabled: false }
    }
  })()
  return pending
}

export function resetActivityCache() { pending = null }
