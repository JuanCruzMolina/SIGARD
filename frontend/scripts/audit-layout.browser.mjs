// Administración v2 · Auditoría (F6.6): visual states of the read-only audit screen.
// Owns its environment like test:alerts:layout:browser: Vite (5173) + the local administrative API
// (8767) in session mode (disposable SQLite, generated admin, generated fictional alerts source).
// Events are generated through the real API (accounts, a fictitious citizen report, preventive
// content, an alert rule, evaluation and decision); only the «API error» state is intercepted.
//   states: list (all categories but «auditoría»), filters in the URL (kept on reload), report
//   updates with status and field names only, page 2, empty, «auditoría» category, API error,
//   Argentina date and time, keyboard; 1440 and 390 px; AA, 44 px, texts ≥ 14 px; no secret in
//   the DOM. Then the integrated demo: the screen shows the «local environment» notice.
// --before: captures only (the previous placeholder), no layout assertions.
// Screenshots (private): data/interim/official/ux-admin-v2-f6-6/<label>/auditoria-<state>-<desktop|mobile>.private.png
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { auditAccessibility, tabReaches } from './browser-a11y.mjs'
import { alertsRuntime, ALERTS_API } from './dev-alerts.mjs'
import { demoRuntime } from './dev-demo.mjs'
import { portAvailable, startDevelopment } from './dev.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const argument = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined
const before = process.argv.includes('--before')
const label = runLabel(argument('--label'))
const frontendRoot = fileURLToPath(new URL('..', import.meta.url))
const outputBase = resolve(frontendRoot, '..', 'data/interim/official/ux-admin-v2-f6-6')
const origin = 'http://127.0.0.1:5173'
for (const port of [5173, 8766, 8767]) assert.ok(await portAvailable(port), `Port ${port} must be free; no existing service will be stopped`)

// Fictitious values that must never reach the audit screen.
const SECRETS = { password: 'contraseña-ficticia-auditoria-1', description: 'Descripción privada ficticia de la prueba de pantalla de auditoría.',
  note: 'Nota interna ficticia que no debe verse en la auditoría.', message: 'Mensaje público ficticio de la prueba de auditoría.',
  body: 'Cuerpo ficticio de la sección para la prueba de auditoría.', comment: 'Comentario ficticio de la decisión en la prueba de auditoría.' }
const AR = new Intl.DateTimeFormat('es-AR', { timeZone: 'America/Argentina/Buenos_Aires', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

const runtime = alertsRuntime({ mode: 'session', source: 'fictional' }); runtime.announce = () => {}
let environment = await startDevelopment(runtime)
let browser
const errors = [], external = [], checks = []
const checkpoint = text => { const name = before ? `captura (sin aserciones de diseño): ${text}` : text; checks.push(name); console.log(`✔ ${name}`) }
try {
  const output = await newRunDirectory(outputBase, label)
  browser = await puppeteer.launch({ headless: true, args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'] })
  const page = await browser.newPage(); page.setDefaultTimeout(30000)
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()) })
  page.on('request', r => { const u = new URL(r.url()); if (/^https?:$/.test(u.protocol) && u.hostname !== '127.0.0.1') external.push(u.origin) })
  let failAudit = false
  const onIntercepted = r => {
    const u = new URL(r.url())
    if (failAudit && r.method() === 'GET' && u.pathname === '/api/v1/admin/audit')
      return r.respond({ status: 500, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': origin }, body: '{"detail":"Fallo ficticio de la auditoría."}' })
    return r.continue()
  }
  const settle = (ms = 400) => delay(ms)
  const noHorizontalScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)
  let token = ''
  const assertNoSecrets = async name => {
    const html = await page.evaluate(() => document.documentElement.outerHTML)
    const leaked = [...Object.values(SECRETS), ...(token ? [token] : [])].filter(secret => html.includes(secret))
    assert.deepEqual(leaked.map(s => `${s.slice(0, 8)}…`), [], `${name}: secretos en el DOM`)
  }
  const shoot = async (name, widths = [['desktop', 1440], ['mobile', 390]]) => {
    await assertNoSecrets(name)
    for (const [kind, width] of widths) {
      await page.setViewport({ width, height: 1000 }); await settle()
      assert.ok(await noHorizontalScroll(), `${name} ${kind}: sin scroll horizontal`)
      await page.screenshot({ path: resolve(output, `auditoria-${name}-${kind}.private.png`), fullPage: true })
    }
    await page.setViewport({ width: 1440, height: 1000 }); await settle(200)
  }
  const mobileChecks = async name => {
    if (before) return
    await page.setViewport({ width: 390, height: 900 }); await settle()
    assert.ok(await noHorizontalScroll(), `${name}: sin scroll horizontal en 390 px`)
    const targets = await page.$$eval('main button, main a[href], main select, main input', e => e
      .filter(x => x.checkVisibility() && x.getBoundingClientRect().width > 0)
      .map(x => { const r = x.getBoundingClientRect(); return [x.getAttribute('aria-label') || x.textContent.trim().slice(0, 30) || x.name || x.tagName, Math.round(r.width), Math.round(r.height)] })
      .filter(([, w, h]) => w < 44 || h < 44))
    assert.deepEqual(targets, [], `${name}: áreas táctiles de 44 px: ${JSON.stringify(targets)}`)
    const small = await page.evaluate(() => {
      const found = [], walker = document.createTreeWalker(document.querySelector('main'), NodeFilter.SHOW_TEXT)
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const e = node.parentElement
        if (!node.textContent.trim() || !e.checkVisibility() || e.closest('svg, option')) continue
        const size = parseFloat(getComputedStyle(e).fontSize); if (size < 14) found.push(`${node.textContent.trim().slice(0, 30)} (${size} px, ${e.className || e.tagName})`)
      }
      return [...new Set(found)]
    })
    assert.deepEqual(small, [], `${name}: textos ≥ 14 px: ${JSON.stringify(small)}`)
    const audit = await auditAccessibility(page, 'main')
    assert.deepEqual(audit.unnamed, [], `${name}: controles con nombre (390)`); assert.deepEqual(audit.lowContrast, [], `${name}: contraste AA (390)`)
    await page.setViewport({ width: 1440, height: 1000 }); await settle(200)
  }
  const desktopAudit = async name => {
    if (before) return
    const audit = await auditAccessibility(page, 'main')
    assert.deepEqual(audit.unnamed, [], `${name}: controles con nombre (1440)`); assert.deepEqual(audit.lowContrast, [], `${name}: contraste AA (1440)`)
  }
  const loaded = () => page.waitForFunction(() => document.querySelector('.audit-results')?.getAttribute('aria-busy') === 'false')
  const search = () => Object.fromEntries(new URL(page.url()).searchParams)
  const api = async (path, options = {}) => {
    const response = await fetch(`${ALERTS_API}${path}`, { ...options, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...options.headers } })
    assert.ok(response.ok, `${path}: ${response.status} ${await response.clone().text()}`)
    return response.headers.get('content-type')?.includes('json') ? response.json() : response.text()
  }
  await page.setViewport({ width: 1440, height: 1000 })

  // Login through the screen, then events through the real API (fictitious values only).
  const { email, password } = runtime.service.credentials
  await page.goto(`${origin}/admin/auditoria`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.admin-login')
  await page.type('.admin-login input[type="email"]', email); await page.type('.admin-login input[type="password"]', password)
  await page.click('.admin-login button')
  await page.waitForFunction(() => document.querySelector('.admin-header h1')?.textContent === 'Auditoría')
  token = await page.evaluate(() => sessionStorage.getItem('sigard_admin_token'))
  if (before) {
    await shoot('antes')
    checkpoint('pantalla anterior (marcador «Próximamente»)')
  } else {
    await api('/api/v1/admin/users', { method: 'POST', body: JSON.stringify({ email: 'auditada-f66@example.test', password: SECRETS.password, current_password: password }) })
    const report = await (await fetch(`${ALERTS_API}/api/v1/citizen-reports`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      category: 'agua_acumulada', description: SECRETS.description, neighborhood: 'Zona Ficticia', latitude: -29.41, longitude: -66.85,
      privacy_accepted: true, privacy_notice_version: '2026-08-19' }) })).json()
    const reports = await api('/api/v1/admin/citizen-reports?page_size=5')
    const reportId = reports.items.find(r => r.tracking_code === report.tracking_code).id
    for (let i = 0; i < 24; i++) await api(`/api/v1/admin/citizen-reports/${reportId}`)
    await api(`/api/v1/admin/citizen-reports/${reportId}`, { method: 'PATCH', body: JSON.stringify({ status: 'en_revision', internal_notes: SECRETS.note, public_status_message: SECRETS.message }) })
    const section = await api('/api/v1/admin/prevention', { method: 'POST', body: JSON.stringify({ slug: 'auditoria-pantalla', title: 'Sección ficticia de auditoría',
      body: SECRETS.body, position: 95, source_label: 'Fuente ficticia', source_url: 'https://example.org/fuente' }) })
    await api(`/api/v1/admin/prevention/${section.id}/publish`, { method: 'POST', body: JSON.stringify({ revision: section.revision }) })
    const status = await api('/api/v1/admin/alerts/status')
    const model = status.models.find(m => m.capability === 'quantity').id
    await api('/api/v1/admin/alerts/rules', { method: 'POST', body: JSON.stringify({ name: 'Regla ficticia de auditoría', capability: 'quantity', model,
      radio_ids: ['FX0000001', 'FX0000002'], threshold: 5, consecutive_weeks: 1, enabled: true }) })
    let pending = []
    for (const week of status.weeks.slice(-8)) {
      await api('/api/v1/admin/alerts/evaluations', { method: 'POST', body: JSON.stringify({ target_week: week.target_week }) })
      pending = await api('/api/v1/admin/alerts/candidates?status=pending'); if (pending.length) break
    }
    assert.ok(pending.length, 'al menos una candidata ficticia')
    await api(`/api/v1/admin/alerts/candidates/${pending[0].id}/discard`, { method: 'POST', body: JSON.stringify({ revision: pending[0].revision, reason: 'false_alarm', comment: SECRETS.comment }) })

    // 1. List (default): newest first, every category but «auditoría», Argentina time, two pages.
    await page.reload({ waitUntil: 'domcontentloaded' }); await loaded()
    const listed = await page.$$eval('.audit-table tbody tr', rows => rows.map(r => ({ category: r.dataset.category, time: r.querySelector('time')?.textContent, iso: r.querySelector('time')?.getAttribute('datetime') })))
    assert.equal(listed.length, 25, 'primera página de 25')
    assert.ok(!listed.some(r => r.category === 'auditoria'), 'la categoría «auditoría» no aparece por defecto')
    const shown = new Set(listed.map(r => r.category))
    assert.ok([...shown].every(c => ['cuentas', 'reportes', 'contenido', 'alertas', 'visor'].includes(c)) && ['alertas', 'contenido', 'reportes'].every(c => shown.has(c)), `categorías: ${[...shown]}`)
    assert.equal(listed[0].time, AR.format(new Date(listed[0].iso)), 'fecha y hora en Argentina')
    const isos = listed.map(r => r.iso); assert.deepEqual(isos, [...isos].sort().reverse(), 'del más reciente al más antiguo')
    assert.deepEqual(await page.$$eval('.ui-breadcrumb a', a => a.map(x => [x.textContent, x.getAttribute('href')])), [['Inicio', '/admin/inicio']])
    assert.deepEqual(await page.$$eval('.audit-table thead th', t => t.map(x => x.textContent)), ['Fecha y hora', 'Categoría', 'Acción', 'Usuario', 'Objeto', 'Detalle'])
    assert.match(await page.$eval('.audit-pagination', e => e.textContent), /Página 1 de [2-9]/)
    assert.match(await page.$eval('.audit-private', e => e.textContent), /nunca contraseñas, notas, comentarios, descripciones ni valores del visor/)
    await desktopAudit('lista'); await shoot('lista'); await mobileChecks('lista')
    checkpoint(`lista: ${listed.length} eventos por página, del más reciente al más antiguo, en hora de Argentina, sin la categoría «auditoría»`)

    // 2. Filters reflected in the URL and kept on reload: reports › update.
    await page.select('#audit-category', 'reportes'); await loaded()
    await page.select('#audit-action', 'update'); await loaded()
    assert.deepEqual(search(), { categoria: 'reportes', accion: 'update' })
    await page.reload({ waitUntil: 'domcontentloaded' }); await loaded()
    assert.deepEqual([await page.$eval('#audit-category', e => e.value), await page.$eval('#audit-action', e => e.value)], ['reportes', 'update'], 'los filtros se recuperan de la URL')
    const update = await page.$eval('.audit-table tbody tr', r => ({ object: r.querySelector('.audit-object').textContent, detail: r.querySelector('.audit-detail').textContent }))
    assert.equal(update.object, `Reporte ${report.tracking_code}`)
    assert.equal(update.detail, 'Estado: Recibido → En revisión · Cambios: estado, mensaje público, nota interna')
    await desktopAudit('filtros'); await shoot('filtros'); await mobileChecks('filtros')
    checkpoint('filtros en la URL (se conservan al recargar); el cambio de un reporte muestra estado y nombres de campos, nunca su texto')

    // 3. Page 2 in the URL; empty state; «auditoría» category on demand.
    await page.goto(`${origin}/admin/auditoria`, { waitUntil: 'domcontentloaded' }); await loaded()
    await page.click('.audit-pagination button:last-child'); await loaded()
    assert.equal(search().pagina, '2')
    await page.reload({ waitUntil: 'domcontentloaded' }); await loaded()
    assert.match(await page.$eval('.audit-pagination', e => e.textContent), /Página 2 de/)
    await page.goto(`${origin}/admin/auditoria?desde=2030-01-01`, { waitUntil: 'domcontentloaded' }); await loaded()
    assert.match(await page.$eval('.audit-results', e => e.textContent), /No hay eventos para estos filtros\./)
    await desktopAudit('vacío'); await shoot('vacio'); await mobileChecks('vacío')
    await page.goto(`${origin}/admin/auditoria?categoria=auditoria`, { waitUntil: 'domcontentloaded' }); await loaded()
    const own = await page.$$eval('.audit-table tbody tr', rows => rows.map(r => [r.dataset.category, r.querySelector('.audit-action').textContent]))
    assert.ok(own.length > 0 && own.every(([c, a]) => c === 'auditoria' && a === 'Auditoría consultada'))
    await shoot('consultas', [['desktop', 1440]])
    checkpoint('página 2 en la URL; estado vacío; la categoría «auditoría» sólo al elegirla')

    // 4. Keyboard: Tab reaches the category filter with a visible focus ring.
    assert.ok(await tabReaches(page, '#audit-category', 120), 'Tab llega al filtro de categoría')
    const ring = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) } })
    assert.ok(ring.style !== 'none' && ring.width >= 2, `foco visible: ${JSON.stringify(ring)}`)
    await page.evaluate(() => document.activeElement?.blur())
    checkpoint('teclado: Tab alcanza los filtros con foco visible')

    // 5. API error (500) → alert with «Reintentar», no invented events.
    await page.setRequestInterception(true); page.on('request', onIntercepted); failAudit = true
    await page.goto(`${origin}/admin/auditoria`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.admin-auditoria [role="alert"]')
    assert.match(await page.$eval('.admin-auditoria [role="alert"]', e => e.textContent), /Fallo ficticio de la auditoría/)
    assert.equal(await page.$('.audit-table tbody tr'), null)
    await desktopAudit('error de API'); await shoot('error-api'); await mobileChecks('error de API')
    failAudit = false; page.off('request', onIntercepted); await page.setRequestInterception(false)
    await page.evaluate(() => [...document.querySelectorAll('main button')].find(b => b.textContent.trim() === 'Reintentar').click()); await loaded()
    checkpoint('error de la API: aviso con el detalle y «Reintentar», sin eventos inventados')
  }
  await page.close()
  await environment.stop(); await environment.closed; environment = undefined

  // 6. Integrated demo: no audit API there; the screen shows the «local environment» notice.
  if (!before) {
    let demoService
    const demo = demoRuntime(); const original = demo.startCompanion
    demo.startCompanion = () => { demoService = original(); return demoService }; demo.announce = () => {}
    environment = await startDevelopment(demo)
    const demoPage = await browser.newPage(); demoPage.setDefaultTimeout(30000)
    demoPage.on('pageerror', e => errors.push(e.message))
    await demoPage.setViewport({ width: 1440, height: 1000 })
    const auditCalls = []
    demoPage.on('request', r => { if (r.url().includes('/api/v1/admin/audit')) auditCalls.push(r.url()) })
    await demoPage.goto(`${origin}/admin/auditoria`, { waitUntil: 'domcontentloaded' })
    await demoPage.waitForSelector('.admin-login')
    await demoPage.type('.admin-login input[type="email"]', demoService.credentials.email); await demoPage.type('.admin-login input[type="password"]', demoService.credentials.password)
    await demoPage.click('.admin-login button')
    await demoPage.waitForSelector('.audit-local-only')
    assert.match(await demoPage.$eval('.audit-local-only', e => e.textContent), /La auditoría se consulta en el entorno local de administración \(npm run dev\)\./)
    assert.deepEqual(auditCalls, [], 'en la demo no se consulta la auditoría')
    await demoPage.screenshot({ path: resolve(output, 'auditoria-demo-desktop.private.png'), fullPage: true })
    checkpoint('demo: aviso «entorno local», sin consultar la auditoría')
  }

  assert.deepEqual(errors, [])
  assert.deepEqual([...new Set(external)].filter(o => !['https://fonts.googleapis.com', 'https://fonts.gstatic.com'].includes(o)), [])
  const receipt = { status: 'passed', label, mode: before ? 'before (captures only)' : 'full', source: 'generated_fictional_only', checks, browser_errors: errors }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify(receipt, null, 2))
} finally {
  await browser?.close()
  if (environment) { await environment.stop(); await environment.closed }
}
