// Real FastAPI + SQLite with generated fixtures. Never starts or queries private A/B.
// Credentials, report codes and research responses stay only in process memory.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { access, mkdir, writeFile, readdir, readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { preview } from 'vite'
import { demoRuntime } from './dev-demo.mjs'
import { portAvailable, startDevelopment } from './dev.mjs'
import { measure, measurements, conditions, exerciseWorkspace } from './thesis-workspace.browser.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const output = resolve(root, 'frontend/.tmp/thesis-closure-ui')
const origin = 'http://127.0.0.1:5173'
const api = 'http://127.0.0.1:8766'
const checks = []
const checkpoint = name => { checks.push(name); console.log(name) }
for (const port of [5173, 5174, 8766]) assert.ok(await portAvailable(port), `Port ${port} must be free; no existing service will be stopped`)
const ownsResearch = await portAvailable(8765)
let session, service, browser, production
const errors = [], unexpectedRequests = []
const startDemo = async () => {
  const runtime = demoRuntime()
  const original = runtime.startCompanion
  runtime.startCompanion = () => { service = original(); return service }
  runtime.announce = () => {} // Never log a credential during an automated check.
  return startDevelopment(runtime)
}
const checkClosed = async directory => {
  assert.ok(await portAvailable(5173)); assert.ok(await portAvailable(8766))
  if (directory) await assert.rejects(access(directory), { code: 'ENOENT' })
  if (ownsResearch) assert.ok(await portAvailable(8765))
  else assert.equal(await portAvailable(8765), false)
}
try {
  await mkdir(output, { recursive: true })
  session = await startDemo()
  await access(resolve(service.directory, 'demo.sqlite3'))
  browser = await puppeteer.launch({ headless: true })
  const page = await browser.newPage()
  page.setDefaultTimeout(15000)
  page.on('pageerror', error => errors.push(error.message))
  let demoRequests = true
  await page.setRequestInterception(true)
  page.on('request', request => {
    const url = new URL(request.url())
    if (['data:', 'blob:'].includes(url.protocol)
      || url.hostname === '127.0.0.1' && ['5173', '5174', '8766'].includes(url.port)) return request.continue()
    if (demoRequests) unexpectedRequests.push(`${url.protocol}//${url.hostname}:${url.port}`)
    return request.abort()
  })
  const fill = async (selector, value) => {
    await page.click(selector)
    await page.keyboard.down('Control'); await page.keyboard.press('KeyA'); await page.keyboard.up('Control')
    await page.keyboard.press('Backspace'); if (value) await page.type(selector, value)
  }
  const clickText = async text => {
    await page.waitForFunction(text => [...document.querySelectorAll('button')].some(button => button.textContent === text && !button.disabled), {}, text)
    await page.evaluate(text => [...document.querySelectorAll('button')].find(button => button.textContent === text && !button.disabled).click(), text)
  }
  await page.setViewport({ width: 1440, height: 1000 })
  await measure('public_map_first_navigation', async () => {
    await page.goto(origin + '/mapa', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.public-radio-control select option:nth-child(264)')
    await page.waitForSelector('.leaflet-overlay-pane path')
  })
  assert.ok(await page.$('.demo-notice'))
  assert.equal(await page.$('.research-spatial'), null)
  const publicRadios = await page.$$eval('.public-radio-control select option', nodes => nodes.slice(1, 6).map(node => node.value))
  for (const radio of publicRadios) await measure('public_map_radio_selection', async () => {
    await page.select('.public-radio-control select', radio)
    await page.waitForFunction(radio => document.querySelector('.radio-details h2')?.textContent.includes(radio), {}, radio)
  })
  for (const [route, selector] of [['/', '.public-home'], ['/validacion', '.validation-panel'], ['/metodologia', '.content-wrap']]) {
    await page.click(`.main-nav a[href="${route}"]`); await page.waitForSelector(selector)
  }
  assert.equal((await fetch(`${api}/api/v1/admin/demo/catalog`)).status, 401)
  checkpoint('Public map with 263 approved radios, keyboard selection and module navigation; private A/B is excluded')

  await page.click('.main-nav a[href="/prevencion"]')
  await page.waitForSelector('.report-form')
  assert.equal(await page.$$eval('.facility-map .leaflet-marker-icon', nodes => nodes.length), 27)
  assert.equal(await page.$eval('.address-search', node => node.disabled), true)
  assert.equal(await page.$eval('.location-help button', node => node.disabled), true)
  for (const width of [1440, 390]) {
    await page.setViewport({ width, height: 1000 })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
    // Taken before filling any report/login; no credential or private result.
    await page.screenshot({ path: resolve(output, `empty-demo-${width}.png`) })
  }
  await page.setViewport({ width: 1440, height: 1000 })
  const disabled = await fetch(`${api}/api/v1/geocoding/address`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address_reference: 'Referencia completamente ficticia' }) })
  assert.equal(disabled.status, 503)
  checkpoint('Prevention and 27 public facilities work offline; desktop/mobile notice; external geocoder and geolocation disabled')

  await page.focus('.report-map'); await page.keyboard.press('Enter')
  await page.click('input[value="agua_acumulada"]')
  await fill('textarea[name="description"]', 'Reporte completamente ficticio para el recorrido académico, sin personas ni hechos reales.')
  await fill('input[name="neighborhood"]', 'Barrio Inventado Demo')
  await page.click('input[name="privacy_accepted"]')
  await page.click('.submit-report')
  await page.waitForSelector('.report-confirmation output')
  const code = await page.$eval('.report-confirmation output', element => element.textContent)
  await page.click('.report-confirmation a')
  await page.click('.status-section button')
  await page.waitForSelector('.status-result')
  assert.match(await page.$eval('.status-result', node => node.textContent), /Recibido/)
  const publicResponse = await (await fetch(`${api}/api/v1/citizen-reports/status/${code}`)).json()
  assert.deepEqual(Object.keys(publicResponse).sort(), ['created_at', 'public_status_message', 'status', 'tracking_code', 'updated_at'])
  checkpoint('Fictitious citizen report created in SQLite; tracking UI and public projection preserve private fields')

  await page.click('.demo-notice a[href="/admin/reportes"]')
  await page.waitForSelector('.admin-login')
  await fill('.admin-login input[type="email"]', service.credentials.email)
  await fill('.admin-login input[type="password"]', service.credentials.password)
  await clickText('Ingresar')
  await page.waitForSelector('.report-inbox > div button')
  await exerciseWorkspace({ page, fill, clickText, checkpoint, output })
  await page.waitForSelector('.report-inbox > div button')
  assert.equal(await page.$$eval('.report-inbox > div button', nodes => nodes.length), 1)
  await page.click('.report-inbox > div button')
  await page.waitForSelector('.private-details')
  assert.ok(await page.$eval('.report-detail h2', (node, expected) => node.textContent === expected, code))
  await page.select('.admin-update select', 'en_revision')
  await fill('.admin-update textarea[maxlength="600"]', 'Revisión ficticia de demostración completada.')
  await fill('.admin-update textarea[maxlength="2000"]', 'Nota interna ficticia que no debe aparecer en seguimiento.')
  await page.click('.admin-update button')
  await page.waitForFunction(() => document.querySelector('.report-detail .status-chip')?.textContent === 'En revisión')
  // Reload the real UI to ensure the update is stored, rather than UI-only state.
  await page.reload({ waitUntil: 'networkidle0' })
  await page.waitForSelector('.report-inbox > div button')
  await page.click('.report-inbox > div button')
  await page.waitForFunction(() => document.querySelector('.report-detail .status-chip')?.textContent === 'En revisión')
  const token = await page.evaluate(() => sessionStorage.getItem('sigard_admin_token'))
  await clickText('Cerrar sesión')
  await page.waitForSelector('.admin-login')
  assert.equal(await page.$('.private-details'), null)
  assert.equal(await page.evaluate(() => sessionStorage.getItem('sigard_admin_token')), null)
  await page.click('.demo-notice a[href="/prevencion#seguimiento"]')
  await page.waitForSelector('#tracking-code')
  await fill('#tracking-code', code)
  await page.click('.status-section button')
  await page.waitForFunction(() => document.querySelector('.status-result')?.textContent.includes('En revisión'))
  const statusText = await page.$eval('.status-result', node => node.textContent)
  assert.match(statusText, /Revisión ficticia de demostración completada/)
  assert.doesNotMatch(statusText, /Nota interna|Barrio Inventado|personas ni hechos/)
  assert.deepEqual(unexpectedRequests, [])
  checkpoint('Session admin authenticated, report updated and reload persisted; logout cleared private UI; citizen sees only public update')

  const previousDirectory = service.directory
  // Detach Vite's HMR client before replacing the server at the same origin.
  // Otherwise its reconnect/reload can abort the next explicit navigation.
  await page.goto('about:blank')
  process.emit('SIGINT')
  assert.equal(await session.closed, 0)
  await checkClosed(previousDirectory)
  session = undefined
  checkpoint('Ctrl+C cleanup removed owned SQLite directory and API/frontend listeners; reused research service respected')
  session = await startDemo()
  assert.equal((await fetch(`${api}/api/v1/citizen-reports/status/${code}`)).status, 404)
  assert.equal((await fetch(`${api}/api/v1/admin/citizen-reports`, { headers: { Authorization: `Bearer ${token}` } })).status, 401)
  await page.goto(origin + '/prevencion', { waitUntil: 'networkidle0' })
  await fill('#tracking-code', code); await page.click('.status-section button')
  await page.waitForSelector('.status-section [role="alert"]')
  assert.equal(await page.$('.status-result'), null)
  const newDirectory = service.directory
  await page.goto('about:blank')
  await session.stop(); assert.equal(await session.closed, 0); await checkClosed(newDirectory)
  session = undefined
  checkpoint('Second demo session starts empty; prior report and admin token are unusable; second SQLite deleted')

  demoRequests = false
  production = await preview({ root: resolve(root, 'frontend'), preview: { host: '127.0.0.1', port: 5174, strictPort: true } })
  let forbiddenProductionRequests = 0
  page.on('request', request => { if (/127\.0\.0\.1:876[56]/.test(request.url())) forbiddenProductionRequests++ })
  for (const path of ['/', '/mapa', '/prevencion', '/admin/reportes']) {
    await page.goto('http://127.0.0.1:5174' + path, { waitUntil: 'networkidle0' })
    assert.equal(await page.$('.demo-notice'), null)
    assert.equal(await page.$('.research-spatial'), null)
    assert.equal(await page.$('.demo-workspace'), null)
  }
  for (const name of await readdir(resolve(root, 'frontend/dist/assets'))) {
    if (name.endsWith('.js')) assert.ok(!(await readFile(resolve(root, 'frontend/dist/assets', name), 'utf8')).includes('127.0.0.1:8766'))
  }
  assert.equal(forbiddenProductionRequests, 0)
  assert.deepEqual(errors, [])
  checkpoint('Production preview keeps public routes with no demo/A-B controls, demo endpoint in JS or experimental requests')
  await writeFile(resolve(output, 'checks.json'), JSON.stringify({ checks, measurements, conditions: await conditions(browser), all_under_five_seconds: measurements.every(row => row.milliseconds < 5000), pageErrors: errors, unexpectedRequests, simulatedResponses: false, postgis: false, privateResearchRead: false }, null, 2))
} finally {
  await browser?.close()
  await session?.stop()
  if (production) await new Promise(resolve => production.httpServer.close(resolve))
}
