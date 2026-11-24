// Administración v2 · Inicio (F5). Owns its environment like test:admin:browser: Vite (5173) + the
// local administrative API (8767) in session mode (disposable SQLite, generated admin kept in memory,
// fictional alerts source). The predictive viewer is fed by the generated fixture (intercepted).
//   1. destination after login: /admin → /admin/inicio; a requested route is respected.
//   2. real API: Inicio's counts equal what the disposable API returns.
//   3. fixtures (intercepted GETs, generated and fictional): with data, empty, one API failing,
//      public map on/off/unknown, and 390 px; no number is ever shown for a missing answer.
//   --capture-only --label <name>: screenshots of /admin/inicio only (before/after comparisons).
// Screenshots (private): data/interim/official/ux-admin-v2-f5/<label>/<screen>-<desktop|mobile>.private.png
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { finalFixtureResponse, candidates as modelCandidates } from '../security/predictive.fixture.mjs'
import { auditAccessibility, tabReaches } from './browser-a11y.mjs'
import { alertsRuntime, ALERTS_API } from './dev-alerts.mjs'
import { portAvailable, startDevelopment } from './dev.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const argument = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined
const captureOnly = process.argv.includes('--capture-only')
const label = runLabel(argument('--label'))
const frontendRoot = fileURLToPath(new URL('..', import.meta.url))
const outputBase = resolve(frontendRoot, '..', 'data/interim/official/ux-admin-v2-f5')
const origin = 'http://127.0.0.1:5173'
for (const port of [5173, 8767]) assert.ok(await portAvailable(port), `Port ${port} must be free; no existing service will be stopped`)

// ---- Generated fictional fixtures (no real radios, reports or content) -------------------------
const day = (n, hour = 10) => new Date(Date.UTC(2026, 9, 1 + n, hour)).toISOString()
const fixtureAlerts = [
  { id: 901, status: 'pending', rule: { name: 'Regla ficticia B' }, radio_id: 'FX0000002', target_week: '2024-03-10', created_at: day(5) },
  { id: 902, status: 'pending', rule: { name: 'Regla ficticia A' }, radio_id: 'FX0000001', target_week: '2024-03-03', created_at: day(1) },
  { id: 903, status: 'pending', rule: { name: 'Regla ficticia A' }, radio_id: 'FX0000003', target_week: '2024-03-17', created_at: day(20) },
]
// 23 received reports, newest first as the API returns them: report k was created on day 30-k.
const fixtureReports = Array.from({ length: 23 }, (_, k) => ({ id: `fict-${k}`, tracking_code: `FICT-${String(k).padStart(4, '0')}`, category: 'agua_acumulada',
  neighborhood: null, status: 'recibido', created_at: day(30 - k, 12), updated_at: day(30 - k, 12) }))
const fixtureSections = [
  { id: 71, title: 'Sección ficticia uno', has_pending_changes: true, updated_at: day(2) },
  { id: 72, title: 'Sección ficticia dos', has_pending_changes: false, updated_at: day(3) },
  { id: 73, title: 'Sección ficticia tres', has_pending_changes: true, updated_at: day(25) },
]
const validActivity = { schema: 'sigard-public-activity/1', generated_at: '2026-11-16', geometry_source: 'inline', source: { kind: 'fixture', fictional: true },
  period: { first_block: '2020-B01', last_block: '2020-B01', start: '2019-12-29', end: '2020-01-25' }, outside_radios: [],
  blocks: [{ id: '2020-B01', year: 2020, block: 1, weeks: [1, 2, 3, 4], start: '2019-12-29', end: '2020-01-25', radios: { 'FICT-001': 'bajo' }, city_weeks: [] }] }

// scenario: null = real API; otherwise { alerts, reports, content, activity, calendar } where each
// is 'data' | 'empty' | 'error' (activity: 'on' | 'off' | 'error'; calendar: 'ok' | 'error').
let scenario = null
const cors = { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Headers': 'Authorization, Content-Type, X-Sigard-Research', 'Access-Control-Allow-Methods': 'GET, POST, PATCH, OPTIONS' }
const json = (status, body) => ({ status, contentType: 'application/json', headers: cors, body: JSON.stringify(body) })
function fixtureResponse(url) {
  const fail = json(500, { detail: 'Fallo ficticio de la prueba' })
  if (url.pathname === '/api/v1/admin/alerts/candidates' && url.searchParams.get('status') === 'pending')
    return scenario.alerts === 'error' ? fail : json(200, scenario.alerts === 'data' ? fixtureAlerts : [])
  if (url.pathname === '/api/v1/admin/alerts/status')
    return scenario.alerts === 'error' ? fail : json(200, { source_available: false, pending: scenario.alerts === 'data' ? fixtureAlerts.length : 0 })
  if (url.pathname === '/api/v1/admin/citizen-reports' && url.searchParams.get('status') === 'recibido') {
    if (scenario.reports === 'error') return fail
    const all = scenario.reports === 'data' ? fixtureReports : [], size = Number(url.searchParams.get('page_size') || 25), page = Number(url.searchParams.get('page') || 1)
    return json(200, { items: all.slice((page - 1) * size, page * size), total: all.length, page, page_size: size })
  }
  if (url.pathname === '/api/v1/admin/prevention')
    return scenario.content === 'error' ? fail : json(200, scenario.content === 'data' ? fixtureSections : fixtureSections.map(s => ({ ...s, has_pending_changes: false })))
  if (url.pathname === '/api/v1/public/activity')
    return scenario.activity === 'on' ? json(200, validActivity) : scenario.activity === 'off' ? json(404, { detail: 'no habilitado' }) : json(503, { detail: 'Fallo ficticio' })
  return null
}

const runtime = alertsRuntime({ mode: 'session', source: 'fictional' }); runtime.announce = () => {}
let environment = await startDevelopment(runtime)
const browser = await puppeteer.launch({ headless: true })
const errors = [], external = [], checks = []
const checkpoint = name => { checks.push(name); console.log(`✔ ${name}`) }
let output
try {
  output = await newRunDirectory(outputBase, label)
  const { email, password } = runtime.service.credentials
  const page = await browser.newPage(); page.setDefaultTimeout(30000)
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()) })
  await page.setRequestInterception(true)
  page.on('request', r => {
    const u = new URL(r.url())
    if (!['http:', 'https:'].includes(u.protocol)) return r.continue()
    if (u.protocol === 'https:' && ['fonts.googleapis.com', 'fonts.gstatic.com'].includes(u.hostname)) return r.continue()
    if (/^[abc]\.tile\.openstreetmap\.org$/.test(u.hostname)) return r.abort()
    if (u.hostname !== '127.0.0.1' || !['5173', '8767'].includes(u.port)) { external.push(u.origin); return r.abort() }
    const predictive = u.pathname.startsWith('/api/v1/research/predictive/')
    if (r.method() === 'OPTIONS' && (predictive || (scenario && fixtureResponse(u)))) return r.respond({ status: 200, headers: cors })
    if (predictive) {
      if (!(r.headers().authorization || '').startsWith('Bearer ')) return r.respond(json(401, { detail: 'Autenticación administrativa requerida' }))
      if (scenario?.calendar === 'error') return r.respond(json(503, { detail: 'Paquete ficticio no verificado' }))
      return r.respond({ status: 200, contentType: 'application/json', headers: cors, body: JSON.stringify(finalFixtureResponse(u.href)) })
    }
    if (scenario && r.method() === 'GET') { const fixture = fixtureResponse(u); if (fixture) return r.respond(fixture) }
    return r.continue()
  })
  const settle = () => new Promise(done => setTimeout(done, 400))
  const noHorizontalScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)
  const shoot = async name => {
    for (const [kind, width] of [['desktop', 1440], ['mobile', 390]]) {
      await page.setViewport({ width, height: 1000 }); await settle()
      assert.ok(await noHorizontalScroll(), `${name} ${kind}: sin scroll horizontal`)
      await page.screenshot({ path: resolve(output, `${name}-${kind}.private.png`), fullPage: true })
    }
    await page.setViewport({ width: 1440, height: 1000 })
  }
  const heading = text => page.waitForFunction(text => document.querySelector('.admin-header h1')?.textContent === text, {}, text)
  const login = async () => {
    await page.waitForSelector('.admin-login')
    await page.type('.admin-login input[type="email"]', email)
    await page.type('.admin-login input[type="password"]', password)
    await page.click('.admin-login button')
  }
  // Inicio has finished loading: no source and no status row still says «Cargando…».
  const homeReady = () => page.waitForFunction(() => document.querySelector('.admin-home') && !document.querySelector('.admin-home [data-source="loading"]')
    && ![...document.querySelectorAll('.home-status-row')].some(e => e.textContent.includes('Cargando')) && document.querySelector('.home-pending')?.getAttribute('aria-busy') === 'false')
  const openHome = async () => { await page.goto(`${origin}/admin/inicio`, { waitUntil: 'domcontentloaded' }); await heading('Inicio'); await homeReady() }
  const counts = () => page.$$eval('.home-attention-row', rows => rows.map(r => r.querySelector('.home-count').textContent))
  const status = () => page.$$eval('.home-status-row', rows => Object.fromEntries(rows.map(r => [r.dataset.status, r.lastElementChild.lastElementChild.textContent])))
  const pending = () => page.$$eval('.home-table tbody tr', rows => rows.map(r => ({ kind: r.dataset.kind, badge: r.cells[0].textContent, icon: Boolean(r.cells[0].querySelector('svg')), detail: r.cells[1].textContent, date: r.cells[2].querySelector('time').getAttribute('datetime'), href: r.cells[3].querySelector('a').getAttribute('href') })))
  await page.setViewport({ width: 1440, height: 1000 })

  if (captureOnly) {
    await page.goto(`${origin}/admin/inicio`, { waitUntil: 'networkidle0' }); await login(); await heading('Inicio'); await settle()
    await shoot('inicio')
    checkpoint(`capturas ${label}`)
  } else {
    // 1. Destination after login.
    await page.goto(`${origin}/admin`, { waitUntil: 'networkidle0' })
    assert.equal(new URL(page.url()).pathname, '/admin/inicio', '/admin sin ruta pedida va a Inicio')
    await login(); await heading('Inicio'); await homeReady()
    assert.equal(new URL(page.url()).pathname, '/admin/inicio', 'tras el ingreso sin ruta pedida queda en /admin/inicio')
    await page.click('.admin-topbar .admin-logout'); await page.waitForSelector('.admin-login')
    await page.goto(`${origin}/admin/cuentas`, { waitUntil: 'networkidle0' }); await login(); await heading('Cuentas administrativas')
    assert.equal(new URL(page.url()).pathname, '/admin/cuentas', 'una ruta pedida se respeta tras el ingreso')
    await page.click('.admin-topbar .admin-logout'); await page.waitForSelector('.admin-login')
    await page.goto(`${origin}/admin/ruta-inexistente`, { waitUntil: 'networkidle0' })
    assert.equal(new URL(page.url()).pathname, '/admin/inicio', 'una ruta desconocida bajo /admin va a Inicio')
    await login(); await heading('Inicio'); await homeReady()
    checkpoint('destino tras el ingreso: /admin → /admin/inicio; /admin/cuentas se respeta; ruta desconocida → Inicio')

    // 2. Real disposable API: the counts are the API's own numbers.
    const token = await page.evaluate(() => sessionStorage.getItem('sigard_admin_token'))
    const api = (path, options = {}) => fetch(`${ALERTS_API}/api/v1/admin${path}`, { ...options, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
      .then(async response => { assert.ok(response.ok, `${path}: ${response.status}`); return response.json() })
    const alertStatus = await api('/alerts/status')
    const model = alertStatus.models.find(m => m.capability === 'quantity').id
    await api('/alerts/rules', { method: 'POST', body: JSON.stringify({ name: 'Regla ficticia de Inicio', capability: 'quantity', model, radio_ids: ['FX0000001', 'FX0000002'], threshold: 5, consecutive_weeks: 1, enabled: true }) })
    for (const week of alertStatus.weeks.slice(-6)) {
      await api('/alerts/evaluations', { method: 'POST', body: JSON.stringify({ target_week: week.target_week }) })
      if ((await api('/alerts/status')).pending > 0) break
    }
    const expected = [(await api('/alerts/candidates?status=pending')).length, (await api('/citizen-reports?status=recibido&page_size=1')).total,
      (await api('/prevention')).filter(s => s.has_pending_changes).length]
    assert.ok(expected[0] > 0, 'la fuente ficticia generó candidatas pendientes')
    await openHome()
    assert.deepEqual(await counts(), expected.map(String), `contadores = API real ${expected}`)
    if (expected[1] + expected[2] === 0) assert.equal((await pending()).filter(i => i.kind === 'alerta').length, Math.min(expected[0], 10))
    const real = await status()
    assert.match(real.datos, /SE 52\/2024/); assert.equal(real.entorno, 'Local')
    checkpoint(`API real descartable: alertas ${expected[0]}, reportes ${expected[1]}, contenido ${expected[2]} iguales a la API`)

    // 3a. Fixtures with data (desktop + 390 px).
    scenario = { alerts: 'data', reports: 'data', content: 'data', activity: 'off', calendar: 'ok' }
    await openHome()
    assert.deepEqual(await counts(), ['3', '23', '2'])
    assert.equal(await page.$eval('.home-badge', e => e.textContent), 'Prototipo experimental — reconstrucción histórica, no uso operativo')
    assert.match(await page.$eval('.home-attention-row', e => e.textContent), /Requiere decisión/)
    assert.deepEqual(await page.$$eval('.home-attention-row a', a => a.map(x => [x.textContent, x.getAttribute('href')])),
      [['Revisar alertas', '/admin/alertas'], ['Abrir bandeja', '/admin/reportes'], ['Ir a contenido', '/admin/contenido']])
    const list = await pending()
    assert.equal(list.length, 10, 'se listan los 10 más antiguos')
    const dates = list.map(i => Date.parse(i.date)); assert.deepEqual(dates, [...dates].sort((a, b) => a - b), 'orden por antigüedad')
    // Oldest overall: alert day 1, content day 2, alert day 5, then reports day 8..14 (k = 22..16).
    assert.deepEqual(list.map(i => i.kind), ['alerta', 'contenido', 'alerta', ...Array(7).fill('reporte')])
    assert.equal(list[0].detail, 'Regla ficticia A · Radio FX0000001 · SE 10/2024')
    assert.equal(list[1].detail, 'Sección «Sección ficticia uno» con cambios sin publicar')
    assert.equal(list[3].detail, 'Agua acumulada · seguimiento FICT-0022', 'el reporte más antiguo sale de la última página')
    for (const item of list) {
      assert.ok(item.icon, 'insignia con ícono'); assert.equal(item.badge, { alerta: 'Alerta', reporte: 'Reporte', contenido: 'Contenido' }[item.kind])
      assert.equal(item.href, { alerta: '/admin/alertas', reporte: '/admin/reportes', contenido: '/admin/contenido' }[item.kind])
    }
    assert.match(await page.$eval('.home-pending', e => e.textContent), /Se muestran los 10 más antiguos de 28/)
    const data = await status()
    assert.match(data.datos, /^Disponibles hasta SE 52\/2024$/)
    assert.equal(data.datos.replace('Disponibles hasta ', ''), await page.$eval('.admin-context [data-week]', e => e.textContent), 'misma semana que el menú')
    assert.equal(data.modelos, `Experimentales · no promovidos para uso operativo (${modelCandidates.length} candidatos)`)
    assert.equal(data.integridad, 'Verificada por la API en esta consulta')
    assert.equal(data.divulgacion, 'Modo protegido · valores menores a 5 ocultos')
    assert.equal(data.mapa, 'Desactivado · la API pública no lo habilita'); assert.equal(data.entorno, 'Local')
    assert.deepEqual(await page.$$eval('.home-quick a', a => a.map(x => x.getAttribute('href'))), ['/admin/predictivo?anio=2024&se=52', '/admin/alertas', '/admin/reportes', '/admin/contenido'])
    const audit = await auditAccessibility(page, '.admin-shell')
    assert.deepEqual(audit.unnamed, [], 'controles con nombre'); assert.deepEqual(audit.lowContrast, [], 'contraste AA')
    // Keyboard: Tab reaches «Revisar alertas» with a visible focus ring; Enter opens Alertas internas.
    assert.ok(await tabReaches(page, '.home-attention-row a[href="/admin/alertas"]'), 'Tab llega a «Revisar alertas»')
    const ring = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) } })
    assert.ok(ring.style !== 'none' && ring.width >= 2, `foco visible: ${JSON.stringify(ring)}`)
    await shoot('inicio-datos')
    // 390 px: no horizontal scroll, 44 px targets, stacked pending rows.
    await page.setViewport({ width: 390, height: 900 }); await settle()
    assert.ok(await noHorizontalScroll())
    const sizes = await page.$$eval('.admin-home a', e => e.filter(x => x.getBoundingClientRect().height > 0).map(x => [x.textContent.trim(), Math.round(x.getBoundingClientRect().width), Math.round(x.getBoundingClientRect().height)]))
    for (const [name, width, height] of sizes) assert.ok(width >= 44 && height >= 44, `área táctil de 44 px: ${name} ${width}×${height}`)
    // Every pending detail wraps inside its card (nothing cut at the right edge).
    const clipped = await page.$$eval('.home-table td', cells => cells.filter(c => c.scrollWidth > c.clientWidth + 1 || c.getBoundingClientRect().right > c.closest('.home-pending').getBoundingClientRect().right).map(c => c.textContent))
    assert.deepEqual(clipped, [], 'detalles sin recortar en 390 px')
    const mobileAudit = await auditAccessibility(page, '.admin-shell')
    assert.deepEqual(mobileAudit.lowContrast, [], 'contraste AA en 390 px')
    assert.ok(parseFloat(await page.$eval('.admin-home .admin-header p', e => getComputedStyle(e).fontSize)) >= 14, 'subtítulo ≥ 14 px')
    await page.keyboard.press('Enter'); await heading('Alertas internas')
    await page.setViewport({ width: 1440, height: 1000 })
    checkpoint('fixture con datos: cantidades, pendientes por antigüedad con insignia, estado del sistema, AA, teclado y 390 px')

    // 3b. Empty: zeros come from the API; the public map probe fails → «No disponible».
    scenario = { alerts: 'empty', reports: 'empty', content: 'empty', activity: 'error', calendar: 'ok' }
    await openHome()
    assert.deepEqual(await counts(), ['0', '0', '0'])
    assert.doesNotMatch(await page.$eval('.home-attention-row', e => e.textContent), /Requiere decisión/)
    assert.equal(await page.$('.home-table'), null)
    assert.match(await page.$eval('.home-pending', e => e.textContent), /No hay pendientes\./)
    assert.equal((await status()).mapa, 'No disponible')
    await shoot('inicio-vacio')
    checkpoint('fixture vacía: ceros de la API, «No hay pendientes.» y mapa público «No disponible» si la API no responde')

    // 3c. One API failing (reports) + unverifiable viewer package; public map enabled.
    scenario = { alerts: 'data', reports: 'error', content: 'data', activity: 'on', calendar: 'error' }
    await openHome()
    assert.deepEqual(await counts(), ['3', 'No disponible', '2'], 'sin respuesta no hay número')
    assert.match(await page.$eval('.home-pending', e => e.textContent), /No disponible: no se pudieron cargar los pendientes de reportes\./)
    assert.deepEqual((await pending()).map(i => i.kind), ['alerta', 'contenido', 'alerta', 'alerta', 'contenido'])
    const failed = await status()
    assert.equal(failed.integridad, 'No verificada · el paquete falta o no pudo verificarse')
    assert.equal(failed.modelos, 'No disponible'); assert.equal(failed.datos, 'No disponible')
    assert.equal(failed.mapa, 'Activado · la API pública sirve el paquete autorizado')
    assert.equal(await page.$eval('.home-quick a', e => e.getAttribute('href')), '/admin/predictivo')
    assert.deepEqual((await auditAccessibility(page, '.admin-shell')).lowContrast, [])
    await shoot('inicio-error')
    checkpoint('fallo de una API: «No disponible» en su cantidad, aviso en pendientes, integridad no verificada y mapa activado')
    scenario = null
  }
  assert.deepEqual(errors, []); assert.deepEqual([...new Set(external)], [])
  const receipt = { status: 'passed', label, capture_only: captureOnly, source: 'generated_fictional_only', checks, browser_errors: errors }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify(receipt, null, 2))
} finally {
  await browser.close()
  if (environment) { await environment.stop(); await environment.closed; environment = undefined }
}
