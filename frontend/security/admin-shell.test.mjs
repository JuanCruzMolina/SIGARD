// Administración v2 (F4): pure helpers of the frame and source contracts of the screens it wraps.
// The browser behaviour (menu, keyboard, 390 px, session bar, counters) is in scripts/admin-shell.browser.mjs.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { catalog } from './predictive.fixture.mjs'
import { ADMIN_GROUPS, ADMIN_HOME, ADMIN_SECTIONS, environmentLabel, epiWeekLabel, epiWeekOf, minutesLeft, rememberFound, sectionForPath, visibleSections } from '../src/services/adminShell.mjs'
import { EMAIL_KEY, endSession, readEmail, SESSION_KEY } from '../src/services/adminSession.mjs'
import { lastEvaluableWeek } from '../src/services/predictiveView.mjs'

const source = path => readFile(new URL(path, import.meta.url), 'utf8')

test('menu: groups, order and routes of the design (Operación / Gestión)', () => {
  assert.deepEqual(ADMIN_GROUPS.map(g => g.label), ['Operación', 'Gestión'])
  assert.deepEqual(ADMIN_SECTIONS.map(s => [s.group, s.label, s.path]), [
    ['operacion', 'Inicio', '/admin/inicio'], ['operacion', 'Módulo predictivo', '/admin/predictivo'],
    ['operacion', 'Alertas internas', '/admin/alertas'], ['operacion', 'Reportes ciudadanos', '/admin/reportes'],
    ['gestion', 'Contenido preventivo', '/admin/contenido'], ['gestion', 'Cuentas', '/admin/cuentas'], ['gestion', 'Auditoría', '/admin/auditoria'],
  ])
  assert.equal(ADMIN_HOME, '/admin/inicio')
  assert.equal(sectionForPath('/admin/predictivo')?.key, 'predictivo')
  assert.equal(sectionForPath('/admin/reportes')?.key, 'reportes')
  assert.equal(sectionForPath('/admin'), null)
  assert.equal(sectionForPath('/admin/reportesx'), null)
})

test('sections per mode: the viewer only in local research, internal alerts never in the demo', () => {
  const keys = mode => visibleSections(mode).map(s => s.key)
  assert.deepEqual(keys({ localResearch: true, demo: false }), ['inicio', 'predictivo', 'alertas', 'reportes', 'contenido', 'cuentas', 'auditoria'])
  assert.deepEqual(keys({ localResearch: false, demo: false }), ['inicio', 'alertas', 'reportes', 'contenido', 'cuentas', 'auditoria'])
  assert.deepEqual(keys({ localResearch: false, demo: true }), ['inicio', 'reportes', 'contenido', 'cuentas', 'auditoria'])
  assert.equal(environmentLabel({ demo: true }), 'Demo ficticia')
  assert.equal(environmentLabel({ localResearch: true, dev: true }), 'Local')
  assert.equal(environmentLabel({ dev: false }), 'Producción')
})

test('epidemiological week of a date matches every week of the predictive calendar fixture', () => {
  assert.ok(catalog.weeks.length > 300)
  for (const week of catalog.weeks) {
    for (const day of [week.target_week, week.target_end]) assert.deepEqual(epiWeekOf(day), { year: week.target_year, week: week.target_epi_week }, day)
  }
  assert.deepEqual(epiWeekOf('2021-01-02'), { year: 2020, week: 53 })
  assert.deepEqual(epiWeekOf('2015-01-03'), { year: 2014, week: 53 })
  assert.equal(epiWeekLabel('2024-06-22'), 'SE 25/2024')
  assert.equal(epiWeekLabel('22/06/2024'), '')
  assert.equal(epiWeekLabel(undefined), '')
})

test('«Datos hasta» in local research = last evaluable week of the viewer, with the SE and year of the API', async () => {
  const last = lastEvaluableWeek(catalog.weeks)
  assert.deepEqual([last.target_year, last.target_epi_week, last.availability_status], [2024, 52, 'available'])
  assert.ok(catalog.weeks.filter(w => w.availability_status === 'available').every(w => w.target_week <= last.target_week))
  assert.equal(epiWeekLabel(last.target_week), `SE ${last.target_epi_week}/${last.target_year}`)
  assert.equal(lastEvaluableWeek([{ target_week: '2024-01-07', availability_status: 'outside_coverage' }]), null)
  assert.equal(lastEvaluableWeek(undefined), null)
  const layout = await source('../src/components/AdminLayout.jsx')
  const has = (text, ...parts) => { for (const part of parts) assert.ok(text.includes(part), part) }
  has(layout, 'const viewerWeek = mode.localResearch && adminSessionActive(token)', 'loadDataWeek(viewerWeek)')
  has(await source('../src/services/adminWeek.js'), 'const last = lastEvaluableWeek(catalog.weeks)',
    'label: `SE ${last.target_epi_week}/${last.target_year}`', 'return viewer ? loadViewerWeek() : loadManifestWeek()')
  has(await source('../src/services/backtestResults.js'), "export async function backtestCalendar(signal) {", "validateBacktestCatalog(await abortable(cached('/calendar'), signal))")
})

test('expiry inside the frame removes token and email; arrival with an expired token too', async () => {
  const has = (text, ...parts) => { for (const part of parts) assert.ok(text.includes(part), part) }
  has(await source('../src/components/AdminLayout.jsx'), 'const expire = () => { endSession(); (onExpire || onLogout)?.() }', 'setTimeout(expire, Math.min(sessionRemaining(token), 2 ** 31 - 1))')
  // F6.6: the Auditoría placeholder of AdminArea became its own screen, with the same arrival check.
  for (const page of ['AdminAuditoria', 'AdminInicio']) has(await source(`../src/pages/${page}.jsx`), 'useEffect(() => { if (!token && readSession()) endSession() }, [token])')
  for (const page of ['AdminReports', 'AdminPredictivo']) has(await source(`../src/pages/${page}.jsx`), 'onExpire={')
})

test('session minutes round up and never go negative', () => {
  assert.equal(minutesLeft(60 * 60000), 60)
  assert.equal(minutesLeft(61000), 2)
  assert.equal(minutesLeft(1), 1)
  assert.equal(minutesLeft(0), 0)
  assert.equal(minutesLeft(-5), 0)
})

test('the login form keeps the email with the token; the session module only reads it and removes both', async () => {
  const values = new Map([[SESSION_KEY, 'token'], [EMAIL_KEY, 'persona@example.invalid']]), storage = { getItem: k => values.get(k) ?? null, removeItem: k => values.delete(k) }
  assert.equal(readEmail(storage), 'persona@example.invalid')
  endSession(storage)
  assert.equal(values.has(SESSION_KEY), false); assert.equal(values.has(EMAIL_KEY), false); assert.equal(readEmail(storage), '')
  assert.equal(readEmail({ getItem() { throw new Error('blocked') } }), '')
  const form = await source('../src/components/AdminLoginForm.jsx')
  for (const text of ['sessionStorage.setItem(SESSION_KEY, token)', 'sessionStorage.setItem(EMAIL_KEY, email)', 'keep(result.access_token, credentials.email.trim())']) assert.ok(form.includes(text), text)
})

test('screens keep their content; the frame replaces header navigation and the duplicated logout', async () => {
  const reports = await source('../src/pages/AdminReports.jsx')
  for (const removed of ['Módulo predictivo', 'Gestionar cuentas', "setPanel('alerts')", "setPanel('prevention')", "setPanel('accounts')"]) assert.ok(!reports.includes(removed), removed)
  for (const kept of ['Exportar CSV', 'Análisis y alertas demo', 'Reportes ciudadanos', 'Información privada.']) assert.ok(reports.includes(kept), kept)
  for (const file of ['AdminAccounts', 'AdminAlerts', 'AdminPrevention']) {
    const text = await source(`../src/components/${file}.jsx`)
    assert.doesNotMatch(text, /Volver a reportes|Cerrar sesión|onBack|onLogout/, file)
  }
  const alerts = await source('../src/components/AdminAlerts.jsx')
  assert.doesNotMatch(alerts, /dev:alerts/); assert.match(alerts, /\(npm run dev\)/)
  const viewer = await source('../src/pages/AdminPredictivo.jsx')
  assert.doesNotMatch(viewer, /admin-predictive-bar/); assert.match(viewer, /<AdminLayout active="predictivo"/)
  const area = await source('../src/pages/AdminArea.jsx')
  for (const path of ['inicio', 'predictivo', 'alertas', 'reportes', 'contenido', 'cuentas', 'auditoria']) assert.match(area, new RegExp(`path="${path}"`))
  assert.match(area, /<Route index element={<Navigate to={ADMIN_HOME} replace\/>}\/>/)
  const css = await source('../src/index.css')
  // F7a: the same families and weights, served by the project (no Google Fonts).
  assert.match(css, /^@import '\.\/fonts\.css';/)
  const fonts = await source('../src/fonts.css')
  for (const face of ['IBM Plex Sans\'; font-style: normal; font-weight: 400', 'IBM Plex Sans\'; font-style: normal; font-weight: 700', 'IBM Plex Mono\'; font-style: normal; font-weight: 500', 'IBM Plex Mono\'; font-style: normal; font-weight: 600']) assert.ok(fonts.includes(face), face)
})

test('counters only come from API answers (pending candidates and received reports), never from constants', async () => {
  const layout = await source('../src/components/AdminLayout.jsx')
  assert.match(layout, /alertsRequest\(token, '\/status', \{ signal \}\)\.then\(status => Number\.isInteger\(status\?\.pending\) \? status\.pending : null\)/)
  assert.match(layout, /listAdminReports\(token, \{ status: 'recibido', page_size: '1' \}/)
  assert.match(layout, /Number\.isInteger\(value\) && value > 0/)
  // F5: the week loaders moved to services/adminWeek.js, shared with Inicio.
  const week = await source('../src/services/adminWeek.js')
  assert.match(layout, /loadDataWeek\(viewerWeek\)/)
  assert.match(week, /fetch\('\/data\/available_weeks\.json'/)
  for (const code of [layout, week]) assert.doesNotMatch(code, /SE \d+\/\d{4}/, 'no hand-written week')
})

test('«Datos hasta»: «—» only while the source has no week; a failure is asked again, a week is kept (F7a)', async () => {
  const answers = [new Error('red caída'), null, { label: 'SE 25/2024' }, { label: 'otra' }]
  let calls = 0
  const load = rememberFound(async () => { const answer = answers[calls++]; if (answer instanceof Error) throw answer; return answer })
  assert.equal(await load(), null, 'falla: sin semana (se muestra «—»)')
  assert.equal(await load(), null, 'vuelve a preguntar; la fuente sin datos sigue sin semana')
  assert.deepEqual(await load(), { label: 'SE 25/2024' }, 'en cuanto la fuente responde, la semana aparece')
  assert.deepEqual(await load(), { label: 'SE 25/2024' }); assert.equal(calls, 3, 'una semana encontrada no se vuelve a pedir')
  const week = await source('../src/services/adminWeek.js')
  assert.ok(week.includes('const loadManifestWeek = rememberFound('))
})

// ---- Inicio (F5) ---------------------------------------------------------------------------
test('Inicio: a source without an answer is «No disponible», never a number', async () => {
  const { countText, NOT_AVAILABLE } = await import('../src/services/adminHome.mjs')
  assert.equal(countText({ status: 'ok', count: 0 }), '0')
  assert.equal(countText({ status: 'ok', count: 7 }), '7')
  assert.equal(countText({ status: 'loading' }), 'Cargando…')
  for (const source of [{ status: 'error' }, { status: 'absent' }, { status: 'ok' }, { status: 'ok', count: '3' }, undefined]) assert.equal(countText(source), NOT_AVAILABLE)
})

test('Inicio: oldest received reports are read from the last page(s) of the newest-first listing', async () => {
  const { oldestReportPages } = await import('../src/services/adminHome.mjs')
  assert.deepEqual(oldestReportPages(0), []); assert.deepEqual(oldestReportPages(10), [])
  assert.deepEqual(oldestReportPages(11), [1, 2]); assert.deepEqual(oldestReportPages(20), [2]); assert.deepEqual(oldestReportPages(23), [2, 3])
  assert.deepEqual(oldestReportPages(null), [])
})

test('Inicio: one pending list, oldest first, with type badges and section links', async () => {
  const { pendingItems } = await import('../src/services/adminHome.mjs')
  const items = pendingItems({
    alerts: { status: 'ok', items: [{ id: 1, rule: { name: 'Regla ficticia' }, radio_id: 'FX0000001', target_week: '2024-03-03', created_at: '2026-10-05T10:00:00Z' }] },
    reports: { status: 'ok', items: [{ id: 'r', tracking_code: 'FICT-0001', category: 'microbasural', created_at: '2026-10-01T10:00:00Z' }] },
    content: { status: 'ok', items: [{ id: 3, title: 'Ficticia', updated_at: '2026-10-03T10:00:00Z' }] },
  })
  assert.deepEqual(items.map(i => [i.kind, i.href, i.detail.join(' · ')]), [
    ['reporte', '/admin/reportes', 'Microbasural · seguimiento FICT-0001'],
    ['contenido', '/admin/contenido', 'Sección «Ficticia» con cambios sin publicar'],
    ['alerta', '/admin/alertas', 'Regla ficticia · Radio FX0000001 · SE 10/2024'],
  ])
  assert.deepEqual(pendingItems({ alerts: { status: 'error' }, reports: { status: 'loading' }, content: { status: 'absent' } }), [])
})

test('Inicio: system state only from API answers', async () => {
  const { integrityText, modelsText, publicMapText, NOT_AVAILABLE } = await import('../src/services/adminHome.mjs')
  assert.equal(publicMapText({ enabled: true }), 'Activado · la API pública sirve el paquete autorizado')
  assert.equal(publicMapText({ enabled: false }), 'Desactivado · la API pública no lo habilita')
  assert.equal(publicMapText({ enabled: false, unavailable: true }), NOT_AVAILABLE)
  assert.equal(modelsText(catalog), `Experimentales · no promovidos para uso operativo (${catalog.experimental_candidates.length} candidatos)`)
  assert.equal(modelsText({}), NOT_AVAILABLE)
  assert.equal(modelsText({ experimental_candidates: [{ promotion: { decision: 'promoted' } }] }), NOT_AVAILABLE)
  assert.equal(integrityText({ viewer: true, catalog }), 'Verificada por la API en esta consulta')
  assert.equal(integrityText({ viewer: true, error: { status: 503 } }), 'No verificada · el paquete falta o no pudo verificarse')
  assert.equal(integrityText({ viewer: true, error: new Error('x') }), NOT_AVAILABLE)
  assert.match(integrityText({ viewer: false }), /^No disponible/)
})

test('Inicio: route, experimental label and no hand-written numbers in the screen', async () => {
  const area = await source('../src/pages/AdminArea.jsx'), home = await source('../src/pages/AdminInicio.jsx')
  assert.match(area, /<Route path="inicio" element={<AdminInicio\/>}\/>/)
  assert.doesNotMatch(area, /inicio: \{ title/)
  const { EXPERIMENTAL_LABEL } = await import('../src/services/adminHome.mjs')
  assert.equal(EXPERIMENTAL_LABEL, 'Prototipo experimental — reconstrucción histórica, no uso operativo')
  assert.doesNotMatch(home, /SE \d+\/\d{4}/, 'la semana no se escribe a mano')
  assert.match(home, /loadDataWeek\(viewer\)/, 'misma fuente de semana que el menú')
})
