// F6.6 · Auditoría: URL state, Argentina time and texts built only from closed lists.
import assert from 'node:assert/strict'
import test from 'node:test'
import { ACTIONS, AUDIT_PAGE_SIZE, CATEGORIES, actionLabel, apiQuery, argentinaDateTime, detailText, filtersFromSearch, objectText,
  searchFromFilters } from '../src/services/adminAudit.mjs'

test('filters ↔ URL: empty values and page 1 stay out; invalid values are ignored', () => {
  assert.equal(searchFromFilters({ category: '', action: '', actor: '', from: '', to: '', page: 1 }).toString(), '')
  const full = { category: 'reportes', action: 'update', actor: '3', from: '2026-03-01', to: '2026-03-10', page: 2 }
  const search = searchFromFilters(full)
  assert.equal(search.toString(), 'categoria=reportes&accion=update&usuario=3&desde=2026-03-01&hasta=2026-03-10&pagina=2')
  assert.deepEqual(filtersFromSearch(search), full, 'ida y vuelta por la URL')
  assert.deepEqual(filtersFromSearch(new URLSearchParams('categoria=inventada&accion=update&usuario=x&desde=10/03/2026&pagina=0')),
    { category: '', action: '', actor: '', from: '', to: '', page: 1 })
  assert.equal(filtersFromSearch(new URLSearchParams('categoria=visor&accion=update')).action, '', 'acción fuera de su categoría')
  assert.equal(searchFromFilters({ category: '', action: 'update', page: 1 }).toString(), '', 'sin categoría no hay acción')
})

test('API query: same filters, fixed page size, never the «auditoría» category unless chosen', () => {
  assert.equal(apiQuery(filtersFromSearch(new URLSearchParams())), `page=1&page_size=${AUDIT_PAGE_SIZE}`)
  assert.equal(apiQuery({ category: 'auditoria', action: '', actor: '', from: '', to: '2026-03-10', page: 3 }),
    `category=auditoria&date_to=2026-03-10&page=3&page_size=${AUDIT_PAGE_SIZE}`)
  assert.ok(Object.keys(CATEGORIES).every(category => Object.keys(ACTIONS[category]).length))
})

test('date and time in Argentina: an event at 23:30 of the last day shows that day', () => {
  assert.equal(argentinaDateTime('2026-03-11T02:30:00+00:00'), new Intl.DateTimeFormat('es-AR', { timeZone: 'America/Argentina/Buenos_Aires',
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date('2026-03-11T02:30:00Z')))
  assert.match(argentinaDateTime('2026-03-11T02:30:00+00:00'), /^10\/03\/2026,? 23:30$/)
})

test('object and detail come only from known fields; unknown keys and free text never appear', () => {
  const update = { category: 'reportes', action: 'update', target: { tracking_code: 'SGD-RPT-ABC123', description: 'texto privado' },
    summary: { status_from: 'recibido', status_to: 'en_revision', changed_fields: ['status', 'internal_notes', 'campo_futuro'], note: 'nota privada' } }
  assert.equal(actionLabel(update), 'Reporte actualizado')
  assert.equal(objectText(update), 'Reporte SGD-RPT-ABC123')
  assert.equal(detailText(update), 'Estado: Recibido → En revisión · Cambios: estado, nota interna')
  assert.equal(detailText({ ...update, summary: { status_from: 'recibido', status_to: 'inventado' } }), '', 'estado fuera de la lista cerrada')
  const discard = { category: 'alertas', action: 'candidate_discarded', target: { radio_id: 'FX0000001', target_week: '2024-04-07' },
    summary: { reason: 'false_alarm', has_comment: true, comment: 'comentario privado' } }
  assert.equal(objectText(discard), 'Radio FX0000001 · semana del 07/04/2024')
  assert.equal(detailText(discard), 'Motivo: Probable falsa alarma · Con comentario')
  assert.equal(detailText({ category: 'visor', action: 'private_query', summary: {} }), 'Valores exactos (modo privado)')
  assert.equal(detailText({ category: 'auditoria', action: 'audit_viewed', summary: { filters: { category: 'reportes', page: 1, secreto: 'x' } } }),
    'Filtros: categoría Reportes, página 1')
  assert.equal(detailText({ category: 'reportes', action: 'export_csv', summary: { count: 1 } }), '1 reporte')
})
