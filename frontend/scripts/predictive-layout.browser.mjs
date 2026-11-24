// Administración v2 · Módulo predictivo (F6.1): visual states of the redesigned screen.
// Owns its environment like test:admin:browser: Vite (5173) + the local administrative API (8767)
// in session mode (disposable SQLite, generated admin). The viewer is fed by the generated
// fictional fixture (intercepted); SIGARD_PRIVATE_VIEW=1 is set for this run only, so the private
// mode can be checked. Nothing real is read.
//   states: loaded (protected / private, ¿Dónde? / ¿Cuántos?), radio chosen from the side list,
//   empty week, API error, loading; desktop 1440 and mobile 390; AA contrast, keyboard, 44 px
//   targets and ≥ 14 px texts on mobile.
// Screenshots (private): data/interim/official/ux-admin-v2-f6/<label>/visor-<state>-<desktop|mobile>.private.png
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { finalFixtureResponse, defaults } from '../security/predictive.fixture.mjs'
import { auditAccessibility, tabReaches } from './browser-a11y.mjs'
import { alertsRuntime } from './dev-alerts.mjs'
import { portAvailable, startDevelopment } from './dev.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const argument = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined
const label = runLabel(argument('--label'))
const frontendRoot = fileURLToPath(new URL('..', import.meta.url))
const outputBase = resolve(frontendRoot, '..', 'data/interim/official/ux-admin-v2-f6')
const origin = 'http://127.0.0.1:5173'
for (const port of [5173, 8767]) assert.ok(await portAvailable(port), `Port ${port} must be free; no existing service will be stopped`)
process.env.SIGARD_PRIVATE_VIEW = '1' // this run's dev server only (private mode selector)

// Interception scenario: 'ok' | 'calendar-error' (503) | 'slow-week' (comparison answered after 4 s).
let scenario = 'ok'
const runtime = alertsRuntime({ mode: 'session', source: 'fictional' }); runtime.announce = () => {}
let environment = await startDevelopment(runtime)
const browser = await puppeteer.launch({ headless: true })
const errors = [], external = [], checks = []
const checkpoint = name => { checks.push(name); console.log(`✔ ${name}`) }
try {
  const output = await newRunDirectory(outputBase, label)
  const { email, password } = runtime.service.credentials
  const page = await browser.newPage(); page.setDefaultTimeout(30000)
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()) })
  await page.setRequestInterception(true)
  page.on('request', async r => {
    const u = new URL(r.url())
    if (!['http:', 'https:'].includes(u.protocol)) return r.continue()
    if (u.protocol === 'https:' && ['fonts.googleapis.com', 'fonts.gstatic.com'].includes(u.hostname)) return r.continue()
    if (/^[abc]\.tile\.openstreetmap\.org$/.test(u.hostname)) return r.abort()
    if (u.hostname !== '127.0.0.1' || !['5173', '8767'].includes(u.port)) { external.push(u.origin); return r.abort() }
    if (u.pathname.startsWith('/api/v1/research/predictive/')) {
      const cors = { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Headers': 'Authorization, X-Sigard-Research', 'Access-Control-Allow-Methods': 'GET' }
      if (r.method() === 'OPTIONS') return r.respond({ status: 200, headers: cors })
      if (!(r.headers().authorization || '').startsWith('Bearer ')) return r.respond({ status: 401, contentType: 'application/json', headers: cors, body: '{"detail":"Autenticación administrativa requerida"}' })
      if (scenario === 'calendar-error' && u.pathname.endsWith('/calendar')) return r.respond({ status: 503, contentType: 'application/json', headers: cors, body: '{"detail":"Paquete ficticio no verificado"}' })
      if (scenario === 'slow-week' && u.pathname.endsWith('/comparison')) await new Promise(done => setTimeout(done, 4000))
      return r.respond({ status: 200, contentType: 'application/json', headers: cors, body: JSON.stringify(finalFixtureResponse(u.href)) }).catch(() => {})
    }
    return r.continue()
  })
  const settle = (ms = 400) => new Promise(done => setTimeout(done, ms))
  const noHorizontalScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)
  const shoot = async (name, widths = [['desktop', 1440], ['mobile', 390]]) => {
    for (const [kind, width] of widths) {
      await page.setViewport({ width, height: 1000 }); await settle()
      assert.ok(await noHorizontalScroll(), `${name} ${kind}: sin scroll horizontal`)
      await page.screenshot({ path: resolve(output, `visor-${name}-${kind}.private.png`), fullPage: true })
    }
    await page.setViewport({ width: 1440, height: 1000 })
  }
  const ready = () => page.waitForFunction(() => document.querySelector('.pv')?.dataset.state === 'ready' && !document.querySelector('.pv-updating'))
  const press = (control, value) => page.click(`[data-control="${control}"] [data-value="${value}"]`)
  const login = async () => {
    await page.waitForSelector('.admin-login')
    await page.type('.admin-login input[type="email"]', email); await page.type('.admin-login input[type="password"]', password)
    await page.click('.admin-login button')
  }
  // Independent expectation of the side list, from the fixture's own comparison response.
  const expectedList = (search, view, mode, model) => {
    const year = Number(new URLSearchParams(search).get('anio')), week = Number(new URLSearchParams(search).get('se'))
    const doc = finalFixtureResponse(`/api/v1/research/predictive/comparison?year=${year}&week=${week}&disclosure=${mode}`)
    const rows = doc.rows.map(r => ({ ...r, ml: r.ml?.[model] || {} }))
    if (view === 'presence') return rows.filter(r => r.availability_status === 'available' && r.common_mask && ['TP', 'FP'].includes(r.ml.confusion))
      .sort((a, b) => (a.ml.topk_rank ?? Infinity) - (b.ml.topk_rank ?? Infinity) || (b.ml.presence_score ?? -1) - (a.ml.presence_score ?? -1) || a.radio_id.localeCompare(b.radio_id))
      .map(r => [r.radio_id, r.ml.confusion === 'TP' ? 'Con registros' : 'Sin registros'])
    return rows.filter(r => r.availability_status === 'available' && r.common_mask && r.ml.quantity !== null && r.ml.quantity !== undefined)
      .sort((a, b) => b.ml.quantity - a.ml.quantity || a.radio_id.localeCompare(b.radio_id)).map(r => [r.radio_id, null])
  }
  const listed = () => page.$$eval('.pv-priority-list button', b => b.map(x => [x.querySelector('.mono:nth-child(2)').textContent, x.querySelector('.pv-priority-status').textContent]))
  const smallTexts = () => page.evaluate(() => {
    const found = [], walker = document.createTreeWalker(document.querySelector('.pv-page'), NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const e = node.parentElement
      if (!node.textContent.trim() || !e.getClientRects().length || e.closest('.leaflet-container, svg, .pv-sr, .pv-hatches, details:not([open]) > :not(summary)')) continue
      const size = parseFloat(getComputedStyle(e).fontSize); if (size < 14) found.push(`${node.textContent.trim().slice(0, 30)} (${size} px, ${e.className || e.tagName})`)
    }
    return [...new Set(found)]
  })
  const smallTargets = () => page.$$eval('.pv-page button, .pv-page a[href], .pv-page select, .pv-page summary', e => e
    .filter(x => x.getClientRects().length && x.getBoundingClientRect().right > 0 && !x.closest('.leaflet-container') && !x.closest('details:not([open]) > :not(summary)'))
    .map(x => { const r = x.getBoundingClientRect(); return [x.textContent.trim().slice(0, 30) || x.getAttribute('aria-label'), Math.round(r.width), Math.round(r.height)] })
    .filter(([, w, h]) => w < 44 || h < 44))
  await page.setViewport({ width: 1440, height: 1000 })

  // 1. Loading: the skeleton shows while the week is requested (comparison delayed 4 s).
  scenario = 'slow-week'
  await page.goto(`${origin}/admin/predictivo?anio=2024&se=15`, { waitUntil: 'domcontentloaded' }); await login()
  await page.waitForSelector('.pv-skeleton')
  assert.match(await page.$eval('.pv', e => e.textContent), /Consultando la semana|Cargando calendario/)
  await shoot('cargando', [['desktop', 1440]])
  await ready(); scenario = 'ok'
  checkpoint('carga: esqueleto y aviso mientras se consulta la semana')

  // 2. Loaded, protected mode, ¿Dónde? with the ML model (default).
  const search = new URL(page.url()).search
  assert.deepEqual(await page.$$eval('.ui-breadcrumb a', a => a.map(x => [x.textContent, x.getAttribute('href')])), [['Inicio', '/admin/inicio']])
  assert.equal(await page.$eval('.ui-breadcrumb [aria-current="page"]', e => e.textContent), 'Módulo predictivo')
  assert.equal(await page.$eval('.admin-header h1', e => e.textContent), 'Predicción semanal de dengue por radio censal')
  assert.equal(await page.$eval('.pv-badge', e => e.textContent), 'Prototipo experimental — reconstrucción histórica, no uso operativo')
  assert.equal(await page.$eval('[data-control="view"] [aria-pressed="true"]', e => getComputedStyle(e).backgroundColor), 'rgb(18, 58, 61)', 'segmentado activo en #123a3d')
  assert.equal(await page.$$eval('.pv-card', c => c.length), 4)
  assert.ok(await page.$eval('.pv-card-value', e => getComputedStyle(e).fontFamily.includes('IBM Plex Mono')), 'cifras en IBM Plex Mono')
  const note = await page.$eval('.pv-note-protected', e => ({ role: e.getAttribute('role'), icon: Boolean(e.querySelector('svg')), text: e.textContent }))
  assert.equal(note.role, 'note'); assert.ok(note.icon); assert.match(note.text, /En modo protegido sólo se muestran radios con 5 o más registros/)
  assert.equal(await page.$eval('#pv-map-title', e => e.textContent), 'Mapa de radios censales')
  assert.equal(await page.$eval('#pv-priority-title', e => e.textContent), 'Radios priorizados esta semana')
  const protectedList = await listed(), protectedExpected = expectedList(search, 'presence', 'presentation', defaults.presence)
  assert.ok(protectedList.length > 0, 'hay radios priorizados visibles')
  assert.deepEqual(protectedList, protectedExpected.slice(0, 10), 'lista = priorizados visibles de la API, por rango')
  assert.ok(protectedList.every(([, status]) => status === 'Con registros'), 'en modo protegido no se listan radios protegidos ni falsas alarmas')
  assert.equal(await page.$eval('.pv-priority-foot a', e => e.getAttribute('href')), '/admin/alertas')
  for (const selector of ['.pv-controls', '.pv-map-card', '.pv-priority', '.pv-evolution', '.pv-section']) assert.equal(await page.$eval(selector, e => getComputedStyle(e).borderTopLeftRadius), '14px', `${selector} como tarjeta`)
  const audit = await auditAccessibility(page, '.admin-shell')
  assert.deepEqual(audit.unnamed, [], 'controles con nombre'); assert.deepEqual(audit.lowContrast, [], 'contraste AA')
  await shoot('donde-protegido')
  checkpoint(`cargado (protegido, ¿Dónde?): encabezado con ruta, controles, 4 tarjetas, aviso, mapa y ${protectedList.length} priorizados visibles iguales a la API`)

  // 3. Side list → radio panel, by mouse and by keyboard.
  await page.click('.pv-priority-list li:first-child button')
  await page.waitForFunction(id => document.querySelector('#pv-panel-title')?.textContent === `Radio censal ${id}`, {}, protectedList[0][0])
  assert.ok(new URL(page.url()).searchParams.get('radio') === protectedList[0][0])
  assert.equal(await page.$eval('.pv-priority-list li:first-child button', e => e.getAttribute('aria-pressed')), 'true')
  await shoot('panel-radio')
  await page.click('.pv-close'); await page.waitForFunction(() => !document.querySelector('.pv-panel'))
  assert.ok(await tabReaches(page, '.pv-priority-list li:nth-child(2) button', 200), 'Tab llega a la lista de priorizados')
  const ring = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) } })
  assert.ok(ring.style !== 'none' && ring.width >= 2, `foco visible: ${JSON.stringify(ring)}`)
  await page.keyboard.press('Enter')
  await page.waitForFunction(id => document.querySelector('#pv-panel-title')?.textContent === `Radio censal ${id}`, {}, protectedList[1][0])
  await page.click('.pv-close'); await page.waitForFunction(() => !document.querySelector('.pv-panel'))
  checkpoint('la lista abre el panel del radio con ratón y con teclado (foco visible)')

  // 4. ¿Cuántos?: list of the highest expected counts among visible radios.
  await press('view', 'quantity'); await ready()
  await page.waitForFunction(() => document.querySelector('#pv-priority-title')?.textContent === 'Radios con más registros esperados')
  const quantityList = await listed(), quantityExpected = expectedList(new URL(page.url()).search, 'quantity', 'presentation', defaults.quantity)
  assert.deepEqual(quantityList.map(([id]) => id), quantityExpected.slice(0, 10).map(([id]) => id))
  assert.ok(quantityList.every(([, status]) => /^\d+(,\d)? esperados$/.test(status)))
  await shoot('cuantos-protegido')
  await press('view', 'presence'); await ready()
  await page.waitForFunction(() => document.querySelector('#pv-priority-title')?.textContent === 'Radios priorizados esta semana')
  checkpoint(`¿Cuántos?: ${quantityList.length} radios con más registros esperados, iguales a la API`)

  // 5. Private mode (SIGARD_PRIVATE_VIEW=1): false alarms appear as «Sin registros».
  await page.click('.pv-advanced > summary')
  await page.select('#bt-disclosure', 'private'); await page.waitForSelector('.pv-private-warning'); await ready()
  const privateList = await listed(), privateExpected = expectedList(new URL(page.url()).search, 'presence', 'private', defaults.presence)
  assert.deepEqual(privateList, privateExpected.slice(0, 10))
  assert.ok(privateList.some(([, status]) => status === 'Sin registros'), 'en modo privado aparecen falsas alarmas')
  await shoot('donde-privado', [['desktop', 1440]])
  await page.select('#bt-disclosure', 'presentation'); await page.waitForFunction(() => !document.querySelector('.pv-private-warning')); await ready()
  checkpoint(`modo privado: ${privateList.filter(([, s]) => s === 'Sin registros').length} falsas alarmas listadas sólo con valores exactos`)

  // 6. Mobile 390: no horizontal scroll, 44 px targets, texts ≥ 14 px, AA.
  await page.setViewport({ width: 390, height: 900 }); await settle()
  assert.ok(await noHorizontalScroll())
  await page.$$eval('.pv-section', s => s.forEach(e => { e.open = true })); await settle()
  const targets = await smallTargets(); assert.deepEqual(targets, [], `áreas táctiles de 44 px en móvil: ${JSON.stringify(targets)}`)
  const texts = await smallTexts(); assert.deepEqual(texts, [], `textos de al menos 14 px en móvil: ${JSON.stringify(texts)}`)
  assert.deepEqual((await auditAccessibility(page, '.admin-shell')).lowContrast, [], 'contraste AA en 390 px')
  await page.$$eval('.pv-section', s => s.forEach(e => { e.open = false }))
  await page.setViewport({ width: 1440, height: 1000 })
  checkpoint('móvil 390 px: sin scroll horizontal, 44 px, textos ≥ 14 px y contraste AA (secciones desplegadas)')

  // 7. Empty week: one explanation card, no map, no side list.
  await page.select('#pv-year', '2021'); await page.waitForSelector('.pv-empty'); await ready()
  assert.match(await page.$eval('.pv-empty', e => e.textContent), /muy pocos registros por radio/)
  assert.equal(await page.$('.pv-map'), null); assert.equal(await page.$('.pv-priority'), null)
  await shoot('semana-vacia')
  checkpoint('semana sin datos divulgables: una explicación, sin mapa ni lista')

  // 8. API error: alert with retry; retry recovers.
  scenario = 'calendar-error'
  await page.goto(`${origin}/admin/predictivo`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.pv-empty[role="alert"]')
  assert.match(await page.$eval('.pv-empty', e => e.textContent), /no pudo verificarse/)
  await shoot('error')
  scenario = 'ok'
  await page.click('.pv-empty button'); await ready()
  checkpoint('error de la API: aviso con «Reintentar» y recuperación')

  assert.deepEqual(errors, []); assert.deepEqual([...new Set(external)], [])
  const receipt = { status: 'passed', label, source: 'generated_fictional_only', checks, browser_errors: errors }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify(receipt, null, 2))
} finally {
  await browser.close()
  if (environment) { await environment.stop(); await environment.closed; environment = undefined }
}
