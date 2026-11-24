// Administración v2 · Reportes ciudadanos (F6.3): visual states of the redesigned screen.
// Owns its environment like test:citizen:browser: Vite (5174) + the disposable SQLite API of
// backend/tests/browser_admin_fixture.py (fictitious admin, no .env, no PostgreSQL, no Docker).
// Fictitious reports are created through the public API; status changes and the CSV export go
// through the screen. Only the «API error» state is intercepted (the list answers 503).
//   states: without reports, with reports (two pages), filters applied, detail open, status change
//   (side-menu counter updated in place), CSV export, API error; desktop 1440 and mobile 390;
//   AA contrast, keyboard, 44 px targets, texts ≥ 14 px on mobile; private fields never in the list.
// --before: captures only (selectors shared with the previous design), no layout assertions.
// Screenshots (private): data/interim/official/ux-admin-v2-f6-3/<label>/reportes-<state>-<desktop|mobile>.private.png
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { auditAccessibility, tabReaches } from './browser-a11y.mjs'
import { proxyRequest } from './browser-proxy.mjs'
import { portAvailable, spawnOwned } from './dev.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const argument = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined
const before = process.argv.includes('--before')
const label = runLabel(argument('--label'))
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const outputBase = resolve(root, 'data/interim/official/ux-admin-v2-f6-3')
const origin = 'http://127.0.0.1:5174'
assert.ok(await portAvailable(5174), 'Port 5174 must be free; no existing service will be stopped')

// Disposable fixture; this run only raises the public creation limit so two pages of reports exist.
const env = { ...process.env, SIGARD_BROWSER_FRONTEND_URL: origin, REPORT_RATE_LIMIT: '100' }
for (const key of Object.keys(env)) if (key.startsWith('PG') || key.startsWith('SIGARD_POSTGIS') || key === 'SIGARD_TEST_POSTGRES_URL') delete env[key]
const fixture = spawn(resolve(root, 'backend/.venv/Scripts/python.exe'), ['-B', 'backend/tests/browser_admin_fixture.py'], { cwd: root, env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] })
const closed = new Promise(done => fixture.once('exit', done))
let serverError = ''
fixture.stderr.on('data', chunk => { serverError += chunk.toString() })
let browser, vite
const errors = [], external = [], checks = []
const checkpoint = text => { const name = before ? `captura (sin aserciones de diseño): ${text}` : text; checks.push(name); console.log(`✔ ${name}`) }
try {
  const ready = await new Promise((done, reject) => {
    let buffer = ''
    const timer = setTimeout(() => reject(new Error('Disposable API did not start')), 15000)
    fixture.once('exit', () => reject(new Error(`Disposable API exited: ${serverError}`)))
    fixture.stdout.on('data', chunk => { buffer += chunk.toString(); if (buffer.includes('\n')) { clearTimeout(timer); done(JSON.parse(buffer.split('\n')[0])) } })
  })
  assert.equal(ready.postgis, false)
  const api = `http://127.0.0.1:${ready.port}`
  vite = spawnOwned(process.execPath, ['frontend/node_modules/vite/bin/vite.js', 'frontend', '--host', '127.0.0.1', '--port', '5174', '--strictPort'], { cwd: root, env: { ...env, VITE_API_URL: 'http://localhost:8000' } })
  for (let attempt = 0; attempt < 100; attempt++) { try { if ((await fetch(origin)).ok) break } catch { /* owned Vite starting */ } await delay(100) }

  const output = await newRunDirectory(outputBase, label)
  browser = await puppeteer.launch({ headless: true })
  const page = await browser.newPage(); page.setDefaultTimeout(15000)
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()) })
  let listFails = false
  await page.setRequestInterception(true)
  page.on('request', async request => {
    const url = new URL(request.url())
    try {
      if (!['http:', 'https:'].includes(url.protocol)) return request.continue()
      if (url.port === '8000' && url.pathname.startsWith('/api/v1/')) {
        if (listFails && request.method() === 'GET' && url.pathname === '/api/v1/admin/citizen-reports' && url.searchParams.get('page_size') !== '1')
          return request.respond({ status: 503, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': origin }, body: JSON.stringify({ detail: 'Fallo ficticio de listado.' }) })
        return proxyRequest(request, api + url.pathname + url.search)
      }
      if (url.hostname === '127.0.0.1' && url.port === '5174') return request.continue()
      if (url.protocol === 'https:' && ['fonts.googleapis.com', 'fonts.gstatic.com'].includes(url.hostname)) return request.continue()
      if (!(url.hostname === '127.0.0.1' && url.port === '8767')) external.push(url.origin) // the alerts API is not part of this run
      return request.abort()
    } catch (error) { if (!request.isInterceptResolutionHandled()) await request.abort().catch(() => {}); errors.push(error.message) }
  })

  const settle = (ms = 400) => delay(ms)
  const noHorizontalScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)
  const shoot = async (name, widths = [['desktop', 1440], ['mobile', 390]]) => {
    for (const [kind, width] of widths) {
      await page.setViewport({ width, height: 1000 }); await settle()
      assert.ok(await noHorizontalScroll(), `${name} ${kind}: sin scroll horizontal`)
      await page.screenshot({ path: resolve(output, `reportes-${name}-${kind}.private.png`), fullPage: true })
    }
    await page.setViewport({ width: 1440, height: 1000 }); await settle(200)
  }
  const fill = async (selector, value) => { await page.click(selector, { count: 3 }); await page.keyboard.press('Backspace'); if (value) await page.type(selector, value) }
  const clickText = text => page.evaluate(text => [...document.querySelectorAll('main button')].find(b => b.textContent.trim() === text && !b.disabled).click(), text)
  const listReady = () => page.waitForFunction(() => document.querySelector('.report-inbox')?.getAttribute('aria-busy') === 'false')
  const rowCodes = () => page.$$eval('.report-inbox button', b => b.map(x => x.textContent.match(/SGD-RPT-[0-9A-Z]{6}/)?.[0]).filter(Boolean))
  const openReport = code => page.evaluate(code => [...document.querySelectorAll('.report-inbox button')].find(b => b.textContent.includes(code)).click(), code)
  const navBadge = () => page.$eval('a.admin-nav-item[href="/admin/reportes"]', a => a.querySelector('.admin-nav-badge')?.textContent ?? '')
  const mobileChecks = async name => {
    if (before) return
    await page.setViewport({ width: 390, height: 900 }); await settle()
    assert.ok(await noHorizontalScroll(), `${name}: sin scroll horizontal en 390 px`)
    const clipped = await page.$eval('.report-inbox', e => e.scrollHeight - e.clientHeight)
    assert.ok(clipped <= 1, `${name}: el listado no queda recortado en 390 px (${clipped} px)`)
    const targets = await page.$$eval('main button, main a[href], main select, main textarea, main input, main summary', e => e
      .filter(x => x.checkVisibility() && x.getBoundingClientRect().right > 0 && !x.closest('.leaflet-container'))
      .map(x => { const r = x.getBoundingClientRect(); return [x.textContent.trim().slice(0, 30) || x.getAttribute('placeholder') || x.tagName, Math.round(r.width), Math.round(r.height)] })
      .filter(([, w, h]) => w < 44 || h < 44))
    assert.deepEqual(targets, [], `${name}: áreas táctiles de 44 px: ${JSON.stringify(targets)}`)
    const small = await page.evaluate(() => {
      const found = [], walker = document.createTreeWalker(document.querySelector('main'), NodeFilter.SHOW_TEXT)
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const e = node.parentElement
        if (!node.textContent.trim() || !e.checkVisibility() || e.closest('svg, option, .leaflet-container')) continue
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
  await page.setViewport({ width: 1440, height: 1000 })

  // 1. Without reports: the fixture starts empty.
  await page.goto(`${origin}/admin/reportes`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.admin-login')
  await page.type('.admin-login input[type="email"]', 'stage14-admin@example.test')
  await page.type('.admin-login input[type="password"]', 'fictitious-initial-password')
  await page.click('.admin-login button'); await listReady()
  await page.waitForSelector('.inbox-empty')
  if (!before) {
    assert.deepEqual(await page.$$eval('.ui-breadcrumb a', a => a.map(x => [x.textContent, x.getAttribute('href')])), [['Inicio', '/admin/inicio']])
    assert.equal(await page.$eval('.admin-header h1', e => e.textContent), 'Reportes ciudadanos')
    assert.equal(await page.$eval('.admin-header p', e => e.textContent), 'Operación interna. Estos registros no son casos de dengue ni evidencia epidemiológica.')
    const notice = await page.$eval('.reports-private', e => ({ role: e.getAttribute('role'), tone: e.classList.contains('ui-notice-warn'), background: getComputedStyle(e).backgroundColor, text: e.textContent }))
    assert.ok(notice.tone && notice.background === 'rgb(251, 241, 210)', `aviso «Información privada» dorado: ${JSON.stringify(notice)}`)
    assert.match(notice.text, /Información privada\. No copies coordenadas exactas a mapas públicos ni herramientas analíticas de terceros\./)
    const padding = await page.$eval('.reports-filters', e => parseFloat(getComputedStyle(e).paddingLeft))
    assert.ok(padding >= 16, `filtros con margen interior (${padding} px)`)
    assert.equal(await page.$eval('.report-detail', e => e.checkVisibility()), true, 'escritorio: el panel «Seleccioná un reporte» se muestra')
    await page.setViewport({ width: 390, height: 900 }); await settle()
    assert.equal(await page.$eval('.report-detail', e => e.checkVisibility()), false, 'móvil: el panel vacío no se muestra sin un reporte elegido')
    assert.ok(await page.$eval('.reports-filters', e => parseFloat(getComputedStyle(e).paddingLeft) >= 14), 'móvil: filtros con margen interior')
    await page.setViewport({ width: 1440, height: 1000 }); await settle(200)
  }
  await desktopAudit('sin reportes')
  await shoot('sin-reportes')
  await mobileChecks('sin reportes')
  checkpoint('sin reportes: ruta, aviso dorado, filtros con margen interior, panel vacío sólo en escritorio')

  // 2. With reports: 27 fictitious reports (two pages of 25) through the public API.
  const categories = ['agua_acumulada', 'microbasural', 'neumaticos_chatarra']
  const created = []
  for (let i = 0; i < 27; i++) {
    const response = await fetch(`${api}/api/v1/citizen-reports`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      category: categories[i % 3], description: `Descripción privada ficticia número ${i + 1} para la prueba de pantalla de reportes.`, neighborhood: `Zona Ficticia ${i % 2 ? 'Par' : 'Impar'}`,
      latitude: -29.41 - i / 1000, longitude: -66.85 - i / 1000, privacy_accepted: true, privacy_notice_version: '2026-08-19' }) })
    assert.equal(response.status, 201, `reporte ficticio ${i + 1}`); created.push({ ...(await response.json()), category: categories[i % 3], index: i })
  }
  await page.reload({ waitUntil: 'domcontentloaded' }); await listReady()
  await page.waitForFunction(() => document.querySelectorAll('.report-inbox button').length > 20)
  const firstPage = await rowCodes()
  assert.equal(firstPage.length, 25, 'primera página de 25')
  await page.waitForFunction(() => document.querySelector('a.admin-nav-item[href="/admin/reportes"] .admin-nav-badge')?.textContent === '27')
  if (!before) {
    assert.deepEqual(await page.$$eval('.report-inbox thead th', t => t.map(x => x.textContent)), ['Código', 'Tipo', 'Recibido', 'Estado'])
    const row = await page.$eval('.report-inbox tbody tr', r => ({ code: getComputedStyle(r.querySelector('button')).fontFamily, badge: r.querySelector('.ui-badge').textContent, icon: Boolean(r.querySelector('.ui-badge svg')), cells: r.cells.length }))
    assert.ok(row.code.includes('IBM Plex Mono') && row.badge === 'Recibido' && row.icon && row.cells === 4, `fila: ${JSON.stringify(row)}`)
    // Privacy: the list never shows descriptions, coordinates or the neighbourhood.
    const listText = await page.$eval('.report-inbox', e => e.textContent)
    assert.ok(!/Descripción privada|Zona Ficticia|-29\.4|-66\.8/.test(listText), 'la lista no expone descripción, barrio ni coordenadas')
    // Pagination: 44 px, AA, and it moves to the second page.
    const pager = await page.$$eval('.report-inbox > footer button', b => b.map(x => { const r = x.getBoundingClientRect(); return [x.textContent, Math.round(r.height), x.disabled] }))
    assert.deepEqual(pager.map(([t, h, d]) => [t, h >= 44, d]), [['Anterior', true, true], ['Siguiente', true, false]])
  }
  await desktopAudit('con reportes')
  await shoot('con-reportes')
  await mobileChecks('con reportes')
  await clickText('Siguiente'); await listReady()
  await page.waitForFunction(() => document.querySelectorAll('.report-inbox button').length < 10)
  assert.equal((await rowCodes()).length, 2, 'segunda página con 2')
  if (!before) await mobileChecks('segunda página')
  await clickText('Anterior'); await listReady(); await page.waitForFunction(() => document.querySelectorAll('.report-inbox button').length > 20)
  checkpoint('con reportes: tabla Código/Tipo/Recibido/Estado, insignias con ícono, 27 en el contador, paginación de 44 px, sin datos privados en la lista')

  // 3. Filters applied: category «Microbasural» (9 of 27).
  await page.select('.admin-filters select', 'microbasural'); await listReady()
  await page.waitForFunction(() => document.querySelectorAll('.report-inbox button').length > 0 && document.querySelectorAll('.report-inbox button').length < 12)
  const filtered = await rowCodes()
  assert.deepEqual(filtered.sort(), created.filter(r => r.category === 'microbasural').map(r => r.tracking_code).sort())
  assert.match(await page.$eval('.report-inbox > header strong', e => e.textContent), /^9 reportes$/)
  await desktopAudit('filtros aplicados')
  await shoot('filtros-aplicados')
  await mobileChecks('filtros aplicados')
  checkpoint(`filtros aplicados: ${filtered.length} reportes de «Microbasural», iguales a la API`)

  // 4. Detail open (by keyboard on desktop): private fields only here.
  const target = created.find(r => r.category === 'microbasural')
  if (!before) {
    assert.ok(await tabReaches(page, '.report-inbox tbody tr:first-child button', 160), 'Tab llega al primer reporte')
    const ring = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) } })
    assert.ok(ring.style !== 'none' && ring.width >= 2, `foco visible: ${JSON.stringify(ring)}`)
    await page.evaluate(() => document.activeElement?.blur())
  }
  await openReport(target.tracking_code)
  await page.waitForSelector('.private-details')
  const detailText = await page.$eval('.report-detail', e => e.textContent)
  assert.ok(detailText.includes(target.tracking_code) && detailText.includes(`Descripción privada ficticia número ${target.index + 1} `))
  if (!before) {
    assert.equal(await page.$eval('.report-detail h2', e => e.textContent), `Reporte ${target.tracking_code}`)
    assert.equal(await page.$eval('.report-detail h2 .report-code', e => e.textContent), target.tracking_code)
    assert.equal(await page.$eval(`.report-inbox tbody tr[aria-selected="true"] button`, e => e.textContent), target.tracking_code)
  }
  await desktopAudit('detalle abierto')
  await shoot('detalle')
  if (!before) {
    // Mobile: choosing a report shows the panel and brings it into view.
    await page.setViewport({ width: 390, height: 900 }); await settle()
    await page.evaluate(() => window.scrollTo(0, 0))
    const other = filtered.find(code => code !== target.tracking_code)
    await openReport(other); await page.waitForFunction(code => document.querySelector('.report-detail h2 .report-code')?.textContent === code, {}, other)
    await settle(600)
    const top = await page.$eval('.report-detail', e => Math.round(e.getBoundingClientRect().top))
    assert.ok(top >= -1 && top < 200, `móvil: el detalle queda a la vista (${top} px)`)
    await page.setViewport({ width: 1440, height: 1000 }); await settle(200)
    await mobileChecks('detalle abierto')
    await openReport(target.tracking_code); await page.waitForFunction(code => document.querySelector('.report-detail h2 .report-code')?.textContent === code, {}, target.tracking_code)
  }
  checkpoint('detalle abierto: descripción y ubicación exacta sólo en el panel protegido; en móvil aparece al elegir y queda a la vista')

  // 5. Status change: «En revisión»; the side-menu counter drops without leaving the section.
  const pageUrl = page.url()
  await page.select('.admin-update select', 'en_revision')
  await fill('.admin-update textarea[maxlength="600"]', 'Revisión ficticia de la prueba de pantalla.')
  await page.click('.admin-update .primary-button')
  await page.waitForFunction(() => document.querySelector('.report-detail :is(.status-chip, .report-status)')?.textContent === 'En revisión')
  await page.waitForFunction(() => document.querySelector('a.admin-nav-item[href="/admin/reportes"] .admin-nav-badge')?.textContent === '26', { timeout: 5000 })
  assert.equal(page.url(), pageUrl, 'sin cambiar de sección')
  assert.equal(await navBadge(), '26')
  await page.waitForFunction(code => { const b = [...document.querySelectorAll('.report-inbox button')].find(x => x.textContent.includes(code)); return Boolean(b) && (b.closest('tr') || b).textContent.includes('En revisión') }, {}, target.tracking_code)
  await desktopAudit('cambio de estado')
  await shoot('cambio-estado')
  await mobileChecks('cambio de estado')
  checkpoint('cambio de estado: «En revisión» en el detalle y la lista; contador del menú 27 → 26 sin cambiar de sección')

  // 6. CSV export with the filter applied.
  await page.evaluate(() => { const original = URL.createObjectURL.bind(URL); URL.createObjectURL = blob => { blob.text().then(text => { window.fictitiousCsv = text }); return original(blob) } })
  const exportResponse = page.waitForResponse(r => r.request().method() === 'GET' && r.url().includes('/citizen-reports/export.csv'))
  await clickText('Exportar CSV')
  const exported = await exportResponse
  assert.equal(exported.status(), 200); assert.equal(new URL(exported.url()).searchParams.get('category'), 'microbasural')
  await page.waitForFunction(() => typeof window.fictitiousCsv === 'string')
  const csv = await page.evaluate(() => window.fictitiousCsv)
  assert.ok(filtered.every(code => csv.includes(code)) && created.filter(r => r.category !== 'microbasural').every(r => !csv.includes(r.tracking_code)), 'CSV = reportes filtrados')
  await page.waitForFunction(() => [...document.querySelectorAll('main button')].some(b => b.textContent.trim() === 'Exportar CSV' && !b.disabled))
  await shoot('exportacion', [['desktop', 1440]])
  checkpoint(`exportación CSV: ${csv.trim().split('\n').length - 1} filas, sólo las del filtro`)

  // 7. API error: the list fails (503) → alert with «Reintentar listado», no invented rows.
  listFails = true
  await fill('.admin-filters input[placeholder="Buscar barrio"]', 'Ficticia')
  await page.waitForSelector('.admin-error [type="button"]')
  assert.match(await page.$eval('.admin-error', e => e.textContent), /Fallo ficticio de listado/)
  assert.equal((await rowCodes()).length, 0)
  await desktopAudit('error de API')
  await shoot('error-api')
  await mobileChecks('error de API')
  listFails = false
  await clickText('Reintentar listado'); await listReady()
  await page.waitForFunction(() => document.querySelectorAll('.report-inbox button').length > 0)
  checkpoint('error de la API: aviso con «Reintentar listado», sin filas inventadas, y recuperación')

  assert.deepEqual(errors, []); assert.deepEqual([...new Set(external)], [])
  const receipt = { status: 'passed', label, mode: before ? 'before (captures only)' : 'full', source: 'generated_fictional_only', sqlite: true, postgis: false, checks, browser_errors: errors }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify(receipt, null, 2))
} finally {
  await browser?.close()
  fixture.stdin.end('stop\n')
  const stopped = await Promise.race([closed.then(() => true), delay(5000).then(() => false)])
  if (!stopped) fixture.kill()
  await vite?.stop().catch(error => { console.error('Owned Vite cleanup:', error.message) })
}
