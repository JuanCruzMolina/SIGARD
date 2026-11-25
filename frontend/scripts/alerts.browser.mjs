// Internal alerts, complete flow in the browser: rule with retrospective preview →
// weekly manual evaluation → candidates → approve/discard → history and audit.
// Default: generated fictional source (12 fictitious radios). --real: the local
// predictive API (read-only, protected values) for private screenshots only.
// Always a disposable SQLite with a generated session admin (credentials in memory).
// Screenshots: data/interim/official/ux-internal-alerts-20261114/<fictional|real>/ (private).
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { access } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { auditAccessibility, tabReaches } from './browser-a11y.mjs'
import { alertsRuntime, ALERTS_API, GOOGLE_FONTS } from './dev-alerts.mjs'
import { portAvailable, startDevelopment } from './dev.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const real = process.argv.includes('--real')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
// Private screenshots: a new folder per run label (SIGARD_SHOTS_LABEL, timestamp by default); never overwritten.
const outputBase = resolve(root, 'data/interim/official/ux-internal-alerts-20261114')
const label = runLabel()
let output
const origin = 'http://127.0.0.1:5173'
const ports = [5173, 8767]
for (const port of ports) assert.ok(await portAvailable(port), `Port ${port} must be free; no existing service will be stopped`)

let session, runtime, browser, page
const errors = [], unexpected = [], failed = []
const checkpoint = name => console.log(`✔ ${name}`)
try {
  output = await newRunDirectory(outputBase, label, real ? 'real' : 'fictional')
  runtime = alertsRuntime({ mode: 'session', source: real ? 'local-research' : 'fictional' })
  runtime.announce = () => {}
  session = await startDevelopment(runtime)
  const service = runtime.service
  const directory = service.directory
  await access(resolve(directory, 'alerts.sqlite3'))
  assert.equal((await fetch(`${ALERTS_API}/api/v1/admin/alerts/status`)).status, 401)
  assert.equal((await fetch(`${ALERTS_API}/api/v1/admin/alerts/rules`, { headers: { Authorization: 'Bearer invalid' } })).status, 401)
  checkpoint('Alerts API rejects anonymous and invalid sessions')

  browser = await puppeteer.launch({ headless: true })
  page = await browser.newPage()
  page.setDefaultTimeout(real ? 120000 : 20000)
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error' && !/Failed to load resource|net::ERR_FAILED/.test(message.text())) errors.push(message.text()) })
  page.on('requestfailed', request => failed.push(`${request.method()} ${request.url()} ${request.failure()?.errorText}`))
  // Observed, not intercepted (interception makes CORS preflights flaky). Like `dev`, the
  // page may load IBM Plex Sans from Google Fonts; any other origin is a failure.
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.protocol === 'https:' && GOOGLE_FONTS.includes(url.hostname)) return
    if (!(['data:', 'blob:'].includes(url.protocol) || url.hostname === '127.0.0.1' && ['5173', '8767'].includes(url.port))) unexpected.push(`${url.protocol}//${url.hostname}:${url.port}`)
  })
  const fill = async (selector, value) => {
    await page.click(selector)
    await page.keyboard.down('Control'); await page.keyboard.press('KeyA'); await page.keyboard.up('Control')
    await page.keyboard.press('Backspace'); if (value) await page.type(selector, value)
  }
  const clickText = async (text, scope = 'body') => {
    await page.waitForFunction((text, scope) => [...document.querySelector(scope).querySelectorAll('button')].some(b => b.textContent.trim() === text && !b.disabled), {}, text, scope)
    await page.evaluate((text, scope) => [...document.querySelector(scope).querySelectorAll('button')].find(b => b.textContent.trim() === text && !b.disabled).click(), text, scope)
  }
  const noHorizontalScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)
  const shoot = async name => {
    for (const [label, width] of [['desktop', 1440], ['mobile', 390]]) {
      await page.setViewport({ width, height: 1000 })
      await new Promise(done => setTimeout(done, 200))
      assert.ok(await noHorizontalScroll(), `${name} ${label} without horizontal scroll`)
      await page.screenshot({ path: resolve(output, `${name}-${label}.private.png`), fullPage: true })
    }
    await page.setViewport({ width: 1440, height: 1000 })
  }
  const tab = async id => { await page.click(`[data-tab="${id}"]`); await page.waitForSelector(`[data-tab="${id}"][aria-pressed="true"]`) }
  const notice = text => page.waitForFunction(text => document.querySelector('.account-notice')?.textContent.includes(text), {}, text)
  const createRule = async ({ name, capability, threshold, radios, weeks }) => {
    await clickText('Nueva regla')
    await fill('.alerts-rule-form input[name="name"]', name)
    await page.click(`.alerts-rule-form input[name="capability"][value="${capability}"]`)
    if (capability === 'quantity') await fill('.alerts-rule-form input[name="threshold"]', threshold)
    if (radios) { await page.click('.alerts-rule-form input[name="scope"][value="selected"]'); await fill('.alerts-rule-form textarea[name="radio_text"]', radios) }
    await page.select('.alerts-rule-form select[name="consecutive_weeks"]', String(weeks))
    assert.equal(await page.$eval('.alerts-rule-form .primary-button', b => b.disabled), true, 'saving requires the retrospective preview first')
    await clickText('Calcular frecuencia histórica', '.alerts-rule-form')
    await page.waitForSelector('[data-preview-activations]')
    const preview = await page.$eval('.alerts-preview', node => node.textContent)
    assert.match(preview, /Frecuencia de activación en 2021–2024 \(reconstrucción retrospectiva; 2024 ya observado\)/)
    assert.match(preview, /Se habría activado \d+ (vez|veces)/)
    return preview
  }
  const decide = async (id, action, comment, reason) => {
    const card = `[data-candidate="${id}"]`
    await clickText(action === 'approve' ? 'Aprobar como aviso interno' : 'Descartar', card)
    if (reason) await page.select(`${card} select`, reason)
    await page.type(`${card} textarea`, comment)
    await clickText(action === 'approve' ? 'Confirmar aprobación' : 'Confirmar descarte', card)
    await notice(action === 'approve' ? 'aprobada como aviso interno' : 'descartada')
    await page.waitForFunction(card => !document.querySelector(`${card}[data-status="pending"]`), {}, card)
  }
  const pendingIds = () => page.$$eval('[data-status="pending"]', nodes => nodes.map(node => node.dataset.candidate))

  await page.setViewport({ width: 1440, height: 1000 })
  await page.goto(origin + '/admin/reportes', { waitUntil: 'networkidle0' })
  await fill('.admin-login input[type="email"]', service.credentials.email)
  await fill('.admin-login input[type="password"]', service.credentials.password)
  await clickText('Ingresar')
  // F4: sections open from the Administración side menu.
  await (await page.waitForSelector('.admin-nav a[href="/admin/alertas"]')).click()
  await page.waitForFunction(() => document.querySelector('.alerts-banner')?.textContent.includes('Ningún algoritmo publica alertas'))
  await page.waitForFunction(() => document.querySelectorAll('.alerts-evaluate option').length > 0)
  for (const width of [1440, 390]) {
    await page.setViewport({ width, height: 1000 })
    const audit = await auditAccessibility(page, 'main')
    assert.deepEqual(audit.unnamed, [], `alertas: controles sin nombre (${width}px)`)
    assert.deepEqual(audit.lowContrast, [], `alertas: contraste insuficiente (${width}px)`)
  }
  await page.setViewport({ width: 1440, height: 1000 })
  assert.ok(await tabReaches(page, '.alerts-evaluate select, .alerts-evaluate button'), 'la evaluación se alcanza con Tab')
  checkpoint('Alerts panel: names, contrast and keyboard reachability')
  await tab('how')
  const how = await page.$eval('.alerts-how', node => node.textContent)
  for (const term of ['Canal', 'Periodicidad', 'Origen del umbral', 'Responsable de aprobación', 'Falsas alarmas', 'automatización queda fuera del alcance']) assert.ok(how.includes(term), term)
  await shoot('01-como-funciona')
  checkpoint('Flow explanation covers channel, periodicity, threshold, approver and false alarms')

  await tab('rules')
  await clickText('Nueva regla')
  await fill('.alerts-rule-form input[name="name"]', 'Umbral inválido')
  await page.click('.alerts-rule-form input[name="capability"][value="quantity"]')
  await fill('.alerts-rule-form input[name="threshold"]', '4')
  await clickText('Calcular frecuencia histórica', '.alerts-rule-form')
  await page.waitForFunction(() => /entre 5 y 1000/.test(document.querySelector('.alerts-rule-form .field-error')?.textContent || ''))
  await clickText('Cancelar', '.alerts-rule-form')
  checkpoint('Threshold below 5 rejected before any request')

  const quantityRule = real
    ? { name: 'Esperados v2 · 2 semanas', capability: 'quantity', threshold: '5', weeks: 2 }
    : { name: 'Esperados ficticios', capability: 'quantity', threshold: '5', radios: 'FX0000001, FX0000002', weeks: 1 }
  const presenceRule = real
    ? { name: 'Prioridad top-10 · 2 semanas', capability: 'presence', weeks: 2 }
    : { name: 'Top-3 ficticio · 3 semanas', capability: 'presence', radios: 'FX0000003', weeks: 3 }
  const preview = await createRule(quantityRule)
  if (!real) assert.match(preview, /43 veces en 29 de 29 semanas evaluables/)
  await shoot('02-regla-vista-previa')
  const rulesSaved = count => page.waitForFunction(count => document.querySelectorAll('[data-rule]').length === count && !document.querySelector('.alerts-rule-form'), {}, count)
  await clickText('Guardar regla', '.alerts-rule-form'); await rulesSaved(1)
  await createRule(presenceRule)
  await clickText('Guardar regla', '.alerts-rule-form'); await rulesSaved(2)
  await shoot('03-reglas')
  checkpoint('Two rules saved after the retrospective activation frequency')

  await tab('pending')
  const weeks = await page.$$eval('.alerts-evaluate option', nodes => nodes.map(node => node.value))
  const first = real ? weeks.at(-1) : '2021-01-31'
  await page.select('.alerts-evaluate select', first)
  await clickText('Evaluar semana'); await notice('candidata(s) nueva(s)')
  if (!real) {
    await page.waitForFunction(() => document.querySelectorAll('[data-status="pending"]').length === 2)
    const observed = await page.$$eval('[data-status="pending"] td[data-observed]', nodes => nodes.map(node => node.textContent))
    assert.ok(observed.length === 2 && observed.every(value => value === 'protegido'), 'observed counts below 5 are protected')
    const expected = await page.$$eval('[data-status="pending"] tbody td:nth-child(2)', nodes => nodes.map(node => node.textContent))
    assert.deepEqual(expected, ['9', '6'])
  }
  await shoot('04-candidatas')
  let ids = await pendingIds()
  if (real && !ids.length) {
    for (const week of weeks.slice(0, -1).reverse().slice(0, 12)) {
      await page.select('.alerts-evaluate select', week); await clickText('Evaluar semana'); await notice('candidata(s) nueva(s)')
      ids = await pendingIds(); if (ids.length >= 2) break
    }
  }
  assert.ok(ids.length >= 1, 'at least one candidate to review')
  const token = await page.evaluate(() => sessionStorage.getItem('sigard_admin_token'))
  const blocked = await page.evaluate(async (api, token, id) => {
    const response = await fetch(`${api}/api/v1/admin/alerts/candidates/${id}/publish`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    return { status: response.status, detail: (await response.json()).detail }
  }, ALERTS_API, token, ids[0])
  assert.equal(blocked.status, 409); assert.match(blocked.detail, /fuera del alcance/)
  checkpoint('Citizen publication refused (409) and audited')

  await decide(ids[0], 'approve', 'Revisado en la reunión semanal (prueba)')
  if (ids[1]) await decide(ids[1], 'discard', 'Sin respaldo de terreno (prueba)', 'false_alarm')
  if (!real) {
    await page.select('.alerts-evaluate select', '2021-02-21')
    await clickText('Evaluar semana'); await notice('2 candidata(s) nueva(s)')
    await page.waitForFunction(() => document.querySelectorAll('[data-status="pending"]').length === 2)
    const radios = await page.$$eval('[data-status="pending"] h3', nodes => nodes.map(node => node.textContent))
    assert.ok(radios.some(text => text.includes('FX0000003')) && radios.some(text => text.includes('FX0000001')))
  }
  await shoot('05-pendientes-tras-revision')
  checkpoint('Approve with comment and discard with reason')

  await tab('history')
  await page.waitForSelector('[data-status="approved_internal"]')
  const actions = await page.$$eval('.alerts-audit li', nodes => nodes.map(node => node.dataset.action))
  for (const action of ['rule_created', 'evaluation_run', 'candidate_approved', 'citizen_publication_blocked']) assert.ok(actions.includes(action), action)
  if (ids[1]) assert.ok(actions.includes('candidate_discarded'))
  assert.match(await page.$eval('[data-status="approved_internal"]', node => node.textContent), /Aviso interno aprobado.*Revisado en la reunión semanal/s)
  await shoot('06-historial-auditoria')
  checkpoint('History and audit record who and when')

  assert.deepEqual(errors, [])
  assert.deepEqual(unexpected, [])
  await page.goto('about:blank')
  await session.stop(); assert.equal(await session.closed, 0); session = undefined
  await assert.rejects(access(directory), { code: 'ENOENT' })
  assert.ok(await portAvailable(8767)); assert.ok(await portAvailable(5173))
  checkpoint('Stopped; disposable SQLite and listeners removed')
  console.log(`Capturas privadas: ${output}`)
} catch (error) {
  // Diagnostic only: visible text of the failing page (fictional or protected values).
  console.error('Failed requests:', failed.filter(f => !/fonts\./.test(f)))
  if (page) console.error((await page.evaluate(() => document.body.innerText).catch(() => '')).slice(0, 1500))
  throw error
} finally {
  await browser?.close()
  if (session) { await session.stop(); await session.closed }
}
