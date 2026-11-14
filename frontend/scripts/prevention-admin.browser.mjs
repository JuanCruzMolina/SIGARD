// dev:demo flow for editable prevention content: real FastAPI + disposable SQLite,
// session-only admin. Edits are fictitious text; credentials stay in memory only.
// Screenshots go to frontend/.tmp/prevention-admin (ignored by Git).
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { access, mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { demoRuntime } from './dev-demo.mjs'
import { portAvailable, startDevelopment } from './dev.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const output = resolve(root, 'frontend/.tmp/prevention-admin')
const origin = 'http://127.0.0.1:5173'
const api = 'http://127.0.0.1:8766'
const editedTitle = 'Prevenir en casa: revisión ficticia de demostración'
const draftMarker = 'Paso ficticio agregado sólo para la demostración.'
for (const port of [5173, 5174, 8766]) assert.ok(await portAvailable(port), `Port ${port} must be free; no existing service will be stopped`)

let session, service, browser
const errors = [], unexpectedRequests = []
const checkpoint = name => console.log(`✔ ${name}`)
try {
  await mkdir(output, { recursive: true })
  const runtime = demoRuntime()
  const original = runtime.startCompanion
  runtime.startCompanion = () => { service = original(); return service }
  runtime.announce = () => {}
  session = await startDevelopment(runtime)
  const directory = service.directory
  await access(resolve(directory, 'demo.sqlite3'))

  const initial = await (await fetch(`${api}/api/v1/public/prevention`)).json()
  assert.equal(initial.initialized, true)
  assert.equal(initial.sections.length, 5)
  assert.equal((await fetch(`${api}/api/v1/admin/prevention`)).status, 401)
  assert.equal((await fetch(`${api}/api/v1/admin/prevention`, { headers: { Authorization: 'Bearer invalid' } })).status, 401)
  checkpoint('Demo API seeded 5 published sections from the static JSON; admin routes reject anonymous access')

  browser = await puppeteer.launch({ headless: true })
  const page = await browser.newPage()
  page.setDefaultTimeout(15000)
  page.on('pageerror', error => errors.push(error.message))
  let blockPreventionApi = false
  await page.setRequestInterception(true)
  page.on('request', request => {
    const url = new URL(request.url())
    if (blockPreventionApi && url.pathname === '/api/v1/public/prevention') return request.abort()
    if (['data:', 'blob:'].includes(url.protocol) || url.hostname === '127.0.0.1' && ['5173', '5174', '8766'].includes(url.port)) return request.continue()
    unexpectedRequests.push(`${url.protocol}//${url.hostname}:${url.port}`)
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
  const noHorizontalScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)
  const shoot = async (name) => {
    for (const [label, width] of [['desktop', 1440], ['mobile', 390]]) {
      await page.setViewport({ width, height: 1000 })
      await new Promise(done => setTimeout(done, 150))
      assert.ok(await noHorizontalScroll(), `${name} ${label} without horizontal scroll`)
      await page.screenshot({ path: resolve(output, `${name}-${label}.png`), fullPage: true })
    }
    await page.setViewport({ width: 1440, height: 1000 })
  }
  const openPublic = async () => {
    await page.goto(origin + '/prevencion', { waitUntil: 'networkidle0' })
    await page.waitForSelector('#prevention-title')
  }

  await page.setViewport({ width: 1440, height: 1000 })
  await openPublic()
  assert.equal(await page.$eval('.content-origin', node => node.dataset.source), 'api')
  assert.equal(await page.$eval('#prevention-title', node => node.textContent), 'Prevenir empieza por eliminar criaderos')
  assert.equal(await page.$$eval('.action-list li', nodes => nodes.length), 7)
  checkpoint('Public page renders the published API sections')

  await page.goto(origin + '/admin/reportes', { waitUntil: 'networkidle0' })
  await fill('.admin-login input[type="email"]', service.credentials.email)
  await fill('.admin-login input[type="password"]', service.credentials.password)
  await clickText('Ingresar')
  await clickText('Contenido preventivo')
  await page.waitForSelector('.prevention-section-list li button')
  assert.equal(await page.$$eval('.prevention-section-list li button', nodes => nodes.length), 5)
  await page.click('.prevention-section-list li button')
  await page.waitForFunction(() => document.querySelector('.prevention-history li')?.textContent.includes('Carga inicial'))
  await fill('.prevention-form input[name="title"]', editedTitle)
  await page.$eval('.prevention-form textarea[name="body"]', textarea => textarea.focus())
  await page.$eval('.prevention-form textarea[name="body"]', textarea => textarea.setSelectionRange(textarea.value.length, textarea.value.length))
  await page.keyboard.type(`\n- ${draftMarker}`)
  await page.waitForFunction(marker => document.querySelector('.prevention-preview')?.textContent.includes(marker), {}, draftMarker)
  // Unsafe text is blocked before reaching the API and leaves the draft untouched.
  await page.keyboard.type(' <script>')
  await clickText('Guardar borrador')
  await page.waitForSelector('.prevention-form .field-error')
  await page.$eval('.prevention-form textarea[name="body"]', textarea => { textarea.focus(); textarea.setSelectionRange(textarea.value.length, textarea.value.length) })
  for (let i = 0; i < ' <script>'.length; i += 1) await page.keyboard.press('Backspace')
  await clickText('Guardar borrador')
  await page.waitForFunction(() => document.querySelector('.admin-prevention .account-notice')?.textContent.includes('Borrador guardado'))
  assert.match(await page.$eval('.prevention-editor p.content-status', node => node.textContent), /cambios sin publicar/)
  await shoot('admin-editor')
  checkpoint('Admin saved a draft with preview; HTML was rejected client-side')

  const draftState = await (await fetch(`${api}/api/v1/public/prevention`)).text()
  assert.ok(!draftState.includes(editedTitle) && !draftState.includes(draftMarker), 'draft must stay private')
  const adminPage = page
  const publicPage = await browser.newPage()
  await publicPage.goto(origin + '/prevencion', { waitUntil: 'networkidle0' })
  await publicPage.waitForSelector('#prevention-title')
  assert.equal(await publicPage.$eval('#prevention-title', node => node.textContent), 'Prevenir empieza por eliminar criaderos')
  await publicPage.close()
  checkpoint('Public page and API keep showing the published version while the draft is pending')

  await clickText('Publicar')
  await adminPage.waitForSelector('.prevention-confirm[role="alertdialog"]')
  assert.match(await page.$eval('.prevention-confirm h3', node => node.textContent), /versión 2/)
  await shoot('admin-confirm')
  await clickText('Confirmar publicación')
  await page.waitForFunction(() => document.querySelector('.admin-prevention .account-notice')?.textContent.includes('Versión 2 publicada'))
  await page.waitForFunction(() => document.querySelector('.prevention-history li strong')?.textContent === 'Publicada')
  const historyText = await page.$eval('.prevention-history', node => node.textContent)
  assert.ok(historyText.includes(service.credentials.email) && /Borrador editado/.test(historyText) && /Carga inicial/.test(historyText))
  checkpoint('Confirmation dialog published version 2; history shows author, dates and edits')

  await openPublic()
  assert.equal(await page.$eval('#prevention-title', node => node.textContent), editedTitle)
  assert.ok((await page.$eval('#prevenir', node => node.textContent)).includes(draftMarker))
  assert.match(await page.$eval('#prevenir .section-source', node => node.textContent), /versión 2/)
  await shoot('public-published')
  checkpoint('Public page shows the newly published version')

  await page.goto(origin + '/admin/reportes', { waitUntil: 'networkidle0' })
  await clickText('Contenido preventivo')
  await page.waitForSelector('.prevention-section-list li button')
  await page.click('.prevention-section-list li button')
  await clickText('Despublicar')
  await clickText('Confirmar despublicación')
  await page.waitForFunction(() => document.querySelector('.admin-prevention .account-notice')?.textContent.includes('dejó de mostrarse'))
  await page.goto(origin + '/prevencion', { waitUntil: 'networkidle0' })
  await page.waitForSelector('#symptoms-title')
  assert.equal(await page.$('.action-list'), null, 'unpublished section is hidden, not replaced by static fallback')
  assert.equal(await page.$('.section-nav a[href="#prevenir"]') !== null, true, 'vector control section keeps the anchor')
  checkpoint('Unpublished section disappears from the public page')

  blockPreventionApi = true
  await page.goto(origin + '/prevencion', { waitUntil: 'networkidle0' })
  await page.waitForSelector('#prevention-title')
  assert.equal(await page.$eval('.content-origin', node => node.dataset.source), 'static')
  assert.equal(await page.$eval('#prevention-title', node => node.textContent), 'Prevenir empieza por eliminar criaderos')
  assert.equal(await page.$('[role="alert"]'), null)
  await shoot('public-static-fallback')
  blockPreventionApi = false
  checkpoint('API unavailable: static JSON fallback without visible errors')

  assert.deepEqual(errors, [])
  assert.deepEqual(unexpectedRequests, [])
  await page.goto('about:blank')
  await session.stop(); assert.equal(await session.closed, 0); session = undefined
  await assert.rejects(access(directory), { code: 'ENOENT' })
  assert.ok(await portAvailable(8766)); assert.ok(await portAvailable(5173))
  checkpoint('Demo stopped; disposable SQLite and listeners removed')
  console.log(`Capturas: ${output}`)
} finally {
  await browser?.close()
  if (session) { await session.stop(); await session.closed }
}
