// Real UI + disposable SQLite API. No Docker, research artifacts or external APIs.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { portAvailable, spawnOwned } from './dev.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const output = resolve(root, 'frontend/.tmp/citizen-flow')
const origin = 'http://127.0.0.1:5174'
assert.ok(await portAvailable(5174), 'Temporary frontend port must be free')
const env = { ...process.env, SIGARD_BROWSER_FRONTEND_URL: origin }
for (const key of Object.keys(env)) if (key.startsWith('PG') || key.startsWith('SIGARD_POSTGIS') || key === 'SIGARD_TEST_POSTGRES_URL') delete env[key]
const fixture = spawn(resolve(root, 'backend/.venv/Scripts/python.exe'), ['-B', 'backend/tests/browser_admin_fixture.py'], { cwd: root, env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] })
const closed = new Promise(resolve => fixture.once('exit', resolve))
let browser, vite, page
const report = { checks: [], pageErrors: [], viewports: [], sqlite: true, postgis: false, researchUsed: false }
let serverError = ''
fixture.stderr.on('data', chunk => { serverError += chunk.toString() })
try {
  const ready = await new Promise((resolve, reject) => {
    let buffer = ''
    const timer = setTimeout(() => reject(new Error('Disposable API did not start')), 15000)
    fixture.once('error', reject)
    fixture.once('exit', () => reject(new Error('Disposable API exited')))
    fixture.stdout.on('data', chunk => {
      buffer += chunk.toString()
      if (buffer.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(buffer.split('\n')[0])) }
    })
  })
  assert.equal(ready.postgis, false)
  const api = `http://127.0.0.1:${ready.port}`
  vite = spawnOwned(process.execPath, ['frontend/node_modules/vite/bin/vite.js', 'frontend', '--host', '127.0.0.1', '--port', '5174', '--strictPort'], { cwd: root, env: { ...env, VITE_API_URL: 'http://localhost:8000' } })
  for (let attempt = 0; attempt < 60; attempt++) {
    try { if ((await fetch(origin)).ok) break } catch { /* owned Vite starting */ }
    await delay(100)
  }
  browser = await puppeteer.launch({ headless: true })
  page = await browser.newPage()
  page.setDefaultTimeout(12000)
  page.on('pageerror', error => report.pageErrors.push(error.message))
  page.on('requestfailed', request => {
    if (request.url().includes('/admin/citizen-reports?')) report.cancelledListRequests = (report.cancelledListRequests || 0) + 1
  })
  let loseCreation = true, holdStatus = false, heldStatus, holdDetail = false, heldDetail
  let listFails = false
  const creationKeys = []
  await page.setRequestInterception(true)
  page.on('request', async request => {
    const url = new URL(request.url())
    try {
      if (url.pathname.startsWith('/api/v1/research')) return request.abort()
      if (url.port === '8000' && url.pathname.startsWith('/api/v1/')) {
        if (url.pathname === '/api/v1/citizen-reports' && request.method() === 'POST') {
          creationKeys.push(request.headers()['idempotency-key'])
          if (loseCreation) {
            loseCreation = false
            const response = await fetch(api + url.pathname, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': creationKeys.at(-1) }, body: request.postData() })
            assert.equal(response.status, 201)
            await response.body.cancel()
            return request.abort('failed')
          }
        }
        if (holdStatus && request.method() === 'GET' && url.pathname.includes('/citizen-reports/status/')) { heldStatus = request; return }
        if (holdDetail && request.method() === 'GET' && /^\/api\/v1\/admin\/citizen-reports\/[^/]+$/.test(url.pathname) && !url.pathname.endsWith('export.csv')) { heldDetail = request; holdDetail = false; return }
        if (listFails && request.method() === 'GET' && url.pathname === '/api/v1/admin/citizen-reports') return request.respond({ status: 503, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': origin }, body: JSON.stringify({ detail: 'Fallo ficticio de listado.' }) })
        return request.continue({ url: api + url.pathname + url.search })
      }
      if (url.protocol.startsWith('http') && !['localhost', '127.0.0.1'].includes(url.hostname)) return request.abort()
      return request.continue()
    } catch (error) {
      if (!request.isInterceptResolutionHandled()) await request.abort().catch(() => {})
      report.interceptionError = error.message
    }
  })
  const fill = async (selector, value) => { await page.click(selector); await page.keyboard.down('Control'); await page.keyboard.press('KeyA'); await page.keyboard.up('Control'); await page.keyboard.press('Backspace'); if (value) await page.type(selector, value) }
  const click = text => page.evaluate(text => [...document.querySelectorAll('button')].find(button => button.textContent === text).click(), text)
  const checkpoint = name => { report.checks.push(name); console.log(name) }
  await mkdir(output, { recursive: true })
  await page.setViewport({ width: 1440, height: 1000 })
  await page.goto(origin + '/prevencion', { waitUntil: 'networkidle0' })
  await page.evaluate(() => Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: success => { window.fictitiousLocationReply = success } } }))
  await click('Usar mi ubicación')
  await page.focus('.report-map'); await page.keyboard.press('Enter')
  const manualPoint = await page.$eval('.coordinate-readout', element => element.textContent)
  await page.evaluate(() => window.fictitiousLocationReply({ coords: { latitude: -29.42, longitude: -66.86 } }))
  assert.equal(await page.$eval('.coordinate-readout', element => element.textContent), manualPoint)
  await page.click('input[value="agua_acumulada"]')
  await fill('textarea[name="description"]', ' '.repeat(20))
  await page.click('input[name="privacy_accepted"]')
  await page.click('.submit-report')
  await page.waitForFunction(() => document.querySelector('.report-form [role="alert"]')?.textContent.includes('20 caracteres'))
  assert.equal(creationKeys.length, 0)
  await fill('textarea[name="description"]', 'Problema completamente ficticio con agua acumulada para verificar el formulario.')
  assert.equal(await page.$('.report-form [role="alert"]'), null)
  await fill('input[name="neighborhood"]', 'Zona Ficticia Uno')
  await page.setViewport({ width: 390, height: 1000 })
  await page.$eval('.report-form', element => element.scrollIntoView())
  await (await page.$('.report-form')).screenshot({ path: resolve(output, 'form-mobile.png') })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.setViewport({ width: 1440, height: 1000 })
  await page.click('.submit-report')
  await page.waitForFunction(() => document.querySelector('.report-form [role="alert"]')?.textContent.includes('Conservamos'))
  assert.match(await page.$eval('textarea[name="description"]', element => element.value), /completamente ficticio/)
  await page.click('.submit-report')
  await page.waitForSelector('.report-confirmation output')
  const code = await page.$eval('.report-confirmation output', element => element.textContent)
  assert.equal(creationKeys[0], creationKeys[1])
  checkpoint('normalized validation, network recovery and idempotent retry')
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: () => Promise.reject(new Error('fictitious denial')) } }))
  await click('Copiar código')
  await page.waitForFunction(() => document.querySelector('.report-confirmation [role="status"]')?.textContent.includes('seleccionado'))
  assert.equal(await page.evaluate(() => window.getSelection().toString()), code)
  await (await page.$('.report-confirmation')).screenshot({ path: resolve(output, 'confirmation-desktop.png') })
  await page.click('.report-confirmation a')
  await page.waitForFunction(() => document.activeElement?.id === 'tracking-code')
  assert.equal(await page.$eval('#tracking-code', element => element.value), code)
  await page.click('.status-section button')
  await page.waitForSelector('.status-result')
  assert.ok(!(await page.$eval('.status-result', element => element.textContent)).includes('Zona Ficticia'))
  await page.setViewport({ width: 390, height: 1000 })
  await (await page.$('.status-section')).screenshot({ path: resolve(output, 'status-mobile.png') })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  await page.setViewport({ width: 1440, height: 1000 })
  await page.screenshot({ path: resolve(output, 'citizen-desktop.png'), fullPage: true })
  checkpoint('copy fallback, tracking focus and private public projection')
  holdStatus = true
  await page.click('.status-section button')
  await page.waitForFunction(() => document.querySelector('.status-section form').getAttribute('aria-busy') === 'true')
  await fill('#tracking-code', 'SGD-RPT-NONE01')
  holdStatus = false
  if (heldStatus) await heldStatus.abort().catch(() => {})
  await page.click('.status-section button')
  await page.waitForSelector('.status-section [role="alert"]')
  assert.equal(await page.$('.status-result'), null)
  checkpoint('code change cancels outdated status and 404 can be retried')

  const second = await (await fetch(api + '/api/v1/citizen-reports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ category: 'microbasural', description: 'Segundo reporte completamente ficticio para comprobar filtros de la bandeja.', neighborhood: 'Zona Ficticia Dos', latitude: -29.418, longitude: -66.856, privacy_accepted: true, privacy_notice_version: '2026-08-19' }) })).json()
  await page.goto(origin + '/admin/reportes', { waitUntil: 'networkidle0' })
  await fill('.admin-login input[type="email"]', 'stage14-admin@example.test')
  await fill('.admin-login input[type="password"]', 'fictitious-initial-password')
  await click('Ingresar')
  await page.waitForFunction(() => document.querySelector('.report-inbox')?.getAttribute('aria-busy') === 'false')
  assert.equal(await page.$$eval('.report-inbox > div button', elements => elements.length), 2)
  holdDetail = true
  await page.click('.report-inbox > div button:first-child')
  await page.click('.report-inbox > div button:last-child')
  await page.waitForSelector('.report-detail h2')
  assert.equal(await page.$eval('.report-detail h2', element => element.textContent), code)
  if (heldDetail) await heldDetail.abort().catch(() => {})
  checkpoint('latest detail wins without stale private selection')
  await fill('.admin-filters input[placeholder="Buscar barrio"]', 'Ficticia Uno')
  await page.waitForFunction(() => document.querySelector('.report-inbox')?.getAttribute('aria-busy') === 'false' && document.querySelectorAll('.report-inbox > div button').length === 1)
  await page.evaluate(() => {
    const original = URL.createObjectURL.bind(URL)
    URL.createObjectURL = blob => {
      blob.text().then(text => { window.fictitiousDownloadedCsv = text })
      return original(blob)
    }
  })
  const exportRequest = page.waitForResponse(response => response.request().method() === 'GET' && response.url().includes('/citizen-reports/export.csv'))
  await click('Exportar CSV')
  const exported = await exportRequest
  assert.ok(new URL(exported.url()).searchParams.get('neighborhood').includes('Ficticia Uno'))
  assert.equal(exported.status(), 200)
  await page.waitForFunction(() => typeof window.fictitiousDownloadedCsv === 'string')
  const csv = await page.evaluate(() => window.fictitiousDownloadedCsv)
  report.exportCheck = { status: exported.status(), firstIncluded: csv.includes(code), secondIncluded: csv.includes(second.tracking_code), rows: csv.split('\n').length }
  assert.ok(csv.includes(code) && !csv.includes(second.tracking_code))
  await fill('.admin-filters input[placeholder="Buscar barrio"]', 'NO-RESULTADOS-FICTICIOS')
  await page.waitForSelector('.inbox-empty')
  await click('Limpiar filtros')
  await page.waitForFunction(() => document.querySelectorAll('.report-inbox > div button').length === 2)
  listFails = true
  await fill('.admin-filters input[placeholder="Buscar barrio"]', 'Ficticia')
  await page.waitForSelector('.admin-error [type="button"]')
  listFails = false
  await click('Reintentar listado')
  await page.waitForFunction(() => document.querySelectorAll('.report-inbox > div button').length === 2)
  checkpoint('filtered CSV, empty list, reset and recovery after 503')
  await page.click('.report-inbox > div button:first-child')
  await page.waitForSelector('.admin-update select')
  await page.select('.admin-update select', 'en_revision')
  await fill('.admin-update textarea[maxlength="600"]', 'Revisión enteramente ficticia completada.')
  await page.click('.admin-update button')
  await page.waitForFunction(() => document.querySelector('.report-detail .status-chip')?.textContent === 'En revisión')
  for (const width of [1440, 390]) {
    await page.setViewport({ width, height: 1000 })
    await page.screenshot({ path: resolve(output, `admin-${width}.png`), fullPage: true })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
    report.viewports.push(width)
  }
  checkpoint('save to real SQLite API and desktop/mobile layout')
  holdDetail = true
  await page.click('.report-inbox > div button:last-child')
  await click('Cerrar sesión')
  if (heldDetail) await heldDetail.abort().catch(() => {})
  await page.waitForSelector('.admin-login')
  assert.equal(await page.$('.private-details'), null)
  assert.equal(await page.evaluate(() => sessionStorage.getItem('sigard_admin_token')), null)
  checkpoint('logout cancels private requests and removes session data')
  assert.deepEqual(report.pageErrors, [])
  assert.equal(report.interceptionError, undefined)
  console.log(JSON.stringify(report))
} catch (error) {
  report.failure = error.message
  console.error(error.stack)
  if (page) await page.screenshot({ path: resolve(output, 'failure.png'), fullPage: true }).catch(() => {})
  throw error
} finally {
  await mkdir(output, { recursive: true })
  await writeFile(resolve(output, 'result.json'), JSON.stringify(report, null, 2))
  await writeFile(resolve(output, 'backend-stderr.log'), serverError)
  await browser?.close()
  fixture.stdin.end('stop\n')
  const stopped = await Promise.race([closed.then(() => true), delay(5000).then(() => false)])
  if (!stopped) fixture.kill()
  await vite?.stop().catch(error => { console.error('Owned Vite cleanup:', error.message) })
  if (serverError && !report.checks.length) console.error('Disposable fixture failed to complete initialization')
}
