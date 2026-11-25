// Complete predictive-module walkthrough. Default is fictional; --real reads local aggregates only.
// F2: owns its environment, like test:alerts:browser: Vite (5173) + the local administrative API
// (8767) in session mode (disposable SQLite, generated admin kept in memory); both ports must be
// free. F3: the viewer lives at /admin/predictivo and needs that admin's session: the walkthrough
// first checks the route without a session (login form, no viewer, no request), logs in through
// that form and finally checks expiry (on use and by timer), a revoked session, a shared link with
// viewer state and an old /mapa link (redirect with a session; public map + link without one).
// Fictional: predictive responses come from the generated fixture (intercepted; the API answers
// 503 without a real module). --real: the real local predictive service behind the same login.
// A previous `npm run build` is needed for the production check.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { preview } from 'vite'
import { finalFixtureResponse } from '../security/predictive.fixture.mjs'
import { PREDICTIVE_ROUTE, SESSION_EXPIRED, SESSION_REQUIRED } from '../src/services/adminSession.mjs'
import { alertsRuntime } from './dev-alerts.mjs'
import { portAvailable, startDevelopment } from './dev.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url), puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const real = process.argv.includes('--real')
// Map tiles: blocked by default (offline mode, no internet dependency); --tiles lets only
// OpenStreetMap tile requests through, after checking they carry nothing but city tile coordinates.
const tilesOnline = process.argv.includes('--tiles')
const OFFLINE_TEXT = 'Mapa de calles no disponible sin conexión'
// Allowed tile area: La Rioja Capital for --real; the generated fictional grid (deliberately
// away from real cartography) otherwise. Both include the map's maxBounds padding.
const CITY = real ? { south: -29.75, north: -29.1, west: -67.2, east: -66.5 } : { south: 9.8, north: 10.4, west: 9.8, east: 10.5 }
const tileLat = (y, z) => Math.atan(Math.sinh(Math.PI * (1 - 2 * y / 2 ** z))) * 180 / Math.PI
const tileLng = (x, z) => x / 2 ** z * 360 - 180
const origin = process.env.SIGARD_MODULE_ORIGIN || 'http://127.0.0.1:5173'
const frontendRoot = fileURLToPath(new URL('..', import.meta.url))
// Private screenshots: a new folder per run label (SIGARD_SHOTS_LABEL, timestamp by default); never overwritten.
const output = await newRunDirectory(resolve(frontendRoot, '..', 'data/interim/official/ux-predictive-redesign-20261112'), runLabel(), real ? 'real' : 'fictional', tilesOnline ? 'con-calles' : 'sin-conexion')
const privateView = process.env.SIGARD_PRIVATE_VIEW === '1'
let assertProtectedMode
for (const port of [5173, 8767]) assert.ok(await portAvailable(port), `Port ${port} must be free; no existing service will be stopped`)
const runtime = alertsRuntime({ mode: 'session', source: real ? 'local-research' : 'fictional' }); runtime.announce = () => {}
let environment = await startDevelopment(runtime)
// --real needs no response altered: requests are only observed, and anything outside 127.0.0.1
// (tiles, unless --tiles; fonts; other hosts) is blocked by the browser's resolver. DevTools request
// interception (the CDP Fetch domain) is left off there: while it is on, Chromium sometimes cancels
// a CORS-preflighted POST (the login) as its preflight completes (net::ERR_FAILED; the server got
// the request and answered 200 with CORS). The fictional run still intercepts: it serves the fixture.
const intercept = !real
const blocked = tilesOnline ? 'MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE *.tile.openstreetmap.org' : 'MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'
const browser = await puppeteer.launch({ headless: true, args: intercept ? [] : [`--host-resolver-rules=${blocked}`] }); let production
const errors = [], external = [], requests = [], timings = [], tileRequests = []
const PROTECTED_NOTE = 'En modo protegido sólo se muestran radios con 5 o más registros'
// Unsigned JWT-shaped administrator values made here (never valid on the server): expired, about
// to expire, and not expired but revoked. The fictional transport rejects them like the server does.
const fakeJwt = (exp, signature = 'FICTIONAL') => `e30.${Buffer.from(JSON.stringify({ sub: '0', role: 'admin', exp })).toString('base64url')}.${signature}`
const viewerUrl = (search = '') => `${origin}${PREDICTIVE_ROUTE}${search}`
try {
  const page = await browser.newPage(); page.setDefaultTimeout(real ? 120000 : 30000)
  assertProtectedMode = async () => {
    if (privateView) return assert.equal(await page.$eval('#bt-disclosure', e => e.value), 'presentation')
    assert.equal(await page.$('#bt-disclosure'), null, 'el selector de valores exactos no debe existir sin SIGARD_PRIVATE_VIEW=1')
    assert.equal(await page.$('option[value="private"]'), null)
    assert.ok(await page.$('[data-disclosure="presentation"]'))
  }
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()) })
  let fail = false
  if (intercept) await page.setRequestInterception(true)
  // Same checks in both modes; without interception the verdicts are only recorded (the resolver blocks).
  const act = { continue: r => intercept ? r.continue() : undefined, abort: r => intercept ? r.abort() : undefined, respond: (r, value) => intercept ? r.respond(value) : undefined }
  page.on('request', async r => {
    const u = new URL(r.url())
    if (!['http:', 'https:'].includes(u.protocol)) return act.continue(r)
    if (/^[abc]\.tile\.openstreetmap\.org$/.test(u.hostname)) {
      const match = /^\/(\d+)\/(\d+)\/(\d+)\.png$/.exec(u.pathname), [z, x, y] = (match || []).slice(1).map(Number)
      assert.ok(match && u.protocol === 'https:' && !u.search && !u.hash && !u.username, `tile request carries only tile coordinates: ${u.href}`)
      assert.ok(z >= 11 && z <= 17, 'tile zoom within the city range')
      assert.ok(tileLat(y + 1, z) <= CITY.north && tileLat(y, z) >= CITY.south && tileLng(x + 1, z) >= CITY.west && tileLng(x, z) <= CITY.east, `tile within the map area: ${z}/${x}/${y}`)
      // OSM's tile policy requires a Referer; send only the origin, never page path, week or radio.
      assert.equal(r.headers().referer, `${origin}/`, 'only the page origin is sent to the tile server')
      assert.equal(r.method(), 'GET'); assert.equal(r.postData(), undefined)
      tileRequests.push(`${z}/${x}/${y}`)
      return tilesOnline ? act.continue(r) : act.abort(r)
    }
    if (u.hostname !== '127.0.0.1' || !['5173', '5174', '8767'].includes(u.port)) { external.push(u.origin); return act.abort(r) }
    if (u.pathname.startsWith('/api/v1/research/')) {
      assert.ok(u.pathname.startsWith('/api/v1/research/predictive/') && u.port === '8767', 'only the authenticated predictive viewer API')
      if (r.method() === 'OPTIONS') return real ? act.continue(r) : act.respond(r, { status: 200, headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Headers': 'Authorization, X-Sigard-Research', 'Access-Control-Allow-Methods': 'GET' } })
      assert.equal(r.method(), 'GET'); requests.push(`${u.pathname}${u.search}`)
      assert.equal(r.headers()['x-sigard-research'], 'local-read')
      // The fixture stands in for the data only: a missing or script-made (revoked) session gets the
      // server's 401; tokens issued by the real login of the session API are accepted.
      const authorization = r.headers().authorization || ''
      if (!real && (!authorization.startsWith('Bearer ') || authorization.endsWith('.FICTIONAL'))) return act.respond(r, { status: 401, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': origin }, body: '{"detail":"Autenticación administrativa requerida"}' })
      if (fail && u.pathname.endsWith('/comparison')) return act.respond(r, { status: 503, headers: { 'Access-Control-Allow-Origin': origin }, body: '{}' })
      if (!real) return act.respond(r, { status: 200, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': origin }, body: JSON.stringify(finalFixtureResponse(u.href)) })
    }
    return act.continue(r)
  })
  // Viewer requests in flight: the viewer keeps loading other years in the background (250 ms apart).
  const viewerInFlight = new Set(); let viewerActivity = Date.now()
  const isViewer = r => r.url().includes(':8767/api/v1/research/') && r.method() !== 'OPTIONS'
  page.on('request', r => {
    // A new document in the main frame (goto, reload): requests of the old one are cancelled with it
    // and, without interception, never report an end; they cannot affect the new page.
    if (r.isNavigationRequest() && r.frame() === page.mainFrame()) viewerInFlight.clear()
    if (isViewer(r)) { viewerInFlight.add(r); viewerActivity = Date.now() }
  })
  const settled = r => { if (viewerInFlight.delete(r)) viewerActivity = Date.now() }
  page.on('requestfinished', settled); page.on('requestfailed', settled)
  // Idle = nothing in flight and nothing new for `quietMs` (well over the 250 ms between loads).
  const viewerIdle = async (quietMs = 1000, limitMs = 60000) => {
    const end = Date.now() + limitMs
    while (viewerInFlight.size || Date.now() - viewerActivity < quietMs) {
      assert.ok(Date.now() < end, `the viewer did not become idle: ${[...viewerInFlight].map(r => r.url()).join(' | ')}`)
      await new Promise(done => setTimeout(done, 100))
    }
  }
  const week = () => page.$eval('.pv', e => e.dataset.week)
  const ready = async previous => {
    await page.waitForFunction(p => { const e = document.querySelector('.pv'); return e && e.dataset.state === 'ready' && (!p || e.dataset.week !== p) }, {}, previous || null)
    await page.waitForFunction(() => !document.querySelector('.pv-updating'))
  }
  const timed = async (operation, action, wait) => { const start = performance.now(); await action(); await wait(); timings.push({ operation, seconds: (performance.now() - start) / 1000 }) }
  const press = (control, value) => page.click(`[data-control="${control}"] [data-value="${value}"]`)
  const text = () => page.$eval('.pv', e => e.innerText)
  const shot = async name => { await new Promise(r => setTimeout(r, 400)); await page.screenshot({ path: resolve(output, `${name}.private.png`), fullPage: false }) }
  const scrollTo = selector => page.$eval(selector, e => e.scrollIntoView({ block: 'start' }))
  // Keyboard path to the radio panel, once the ¿Dónde? layer has replaced any previous one.
  const openRadioWithKeyboard = async () => {
    await page.waitForFunction(() => document.querySelector('[data-legend="TP"]') && document.querySelectorAll('.pv-map').length === 1 && document.querySelector('.pv-map path[tabindex="0"]'))
      .catch(async error => {
        const state = await page.evaluate(() => ({ legend: !!document.querySelector('[data-legend="TP"]'), maps: document.querySelectorAll('.pv-map').length,
          paths: document.querySelectorAll('.pv-map path').length, focusable: document.querySelectorAll('.pv-map path[tabindex="0"]').length,
          state: document.querySelector('.pv')?.dataset.state, url: location.search }))
        throw new Error(`${error.message} ${JSON.stringify(state)}`)
      })
    await new Promise(r => setTimeout(r, 300))
    await page.$eval('.pv-map path[tabindex="0"]', e => e.focus()); await page.keyboard.press('Enter'); await page.waitForSelector('.pv-panel')
  }
  const noHorizontalScroll = async () => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)

  await page.setViewport({ width: 1440, height: 1000 })
  // Session (F2/F3): without one, /admin/predictivo shows the Administración login, no viewer and no request.
  const loginNotice = async text => {
    await page.waitForFunction(t => document.querySelector('.admin-login [role="status"]')?.textContent === t, {}, text)
    assert.equal(await page.$('.pv'), null, 'no viewer without an administrator session')
  }
  const loginForm = async () => {
    await page.type('.admin-login input[type="email"]', runtime.service.credentials.email)
    await page.type('.admin-login input[type="password"]', runtime.service.credentials.password)
    await page.click('.admin-login .primary-button')
  }
  const clearSession = () => page.evaluate(() => sessionStorage.removeItem('sigard_admin_token'))
  await page.goto(viewerUrl(), { waitUntil: 'domcontentloaded' })
  await loginNotice(SESSION_REQUIRED); assert.equal(requests.length, 0)
  assert.equal(await page.$('.main-nav a[href="/admin/predictivo"]'), null)
  assert.doesNotMatch(await page.$eval('.main-nav', e => e.textContent), /Módulo predictivo/)
  await shot('desktop-sin-sesion')
  // Logging in through the form stays on /admin/predictivo and opens the viewer.
  await loginForm(); await ready()
  assert.equal(new URL(page.url()).pathname, PREDICTIVE_ROUTE)
  // Cold start with the session already open (as before F3).
  await timed('cold_start_until_default_week_rendered', () => page.goto(viewerUrl(), { waitUntil: 'domcontentloaded' }), () => ready())
  const defaultWeek = await week()
  if (!real) assert.equal(defaultWeek, '2024-04-07', 'fictional default is the week with most disclosable radios')
  assert.ok(timings[0].seconds < 5, `cold start under 5 s (${timings[0].seconds.toFixed(2)} s)`)
  assert.equal(new URL(page.url()).pathname, PREDICTIVE_ROUTE)
  // Model selector built from metadata: corrective v2 by default, v1 candidates still available.
  assert.equal(await page.$eval('[data-control="model"] select', e => e.value), 'rf_v2_city_propensity')
  assert.deepEqual(await page.$$eval('[data-control="model"] option', o => o.map(e => e.value)), ['rf_A_epi_climate', 'rf_v2_city_propensity'])
  assert.match(await page.$eval('.pv-model-rule', e => e.textContent), /Marca los 10 radios con mayor prioridad cada semana/)
  assert.match(page.url(), /anio=\d{4}&se=\d+/)
  await assertProtectedMode()
  assert.equal(await page.$eval('.pv-badge', e => e.textContent), 'Prototipo experimental — reconstrucción histórica, no uso operativo')
  const protectedText = await text()
  assert.match(protectedText, new RegExp(PROTECTED_NOTE))
  assert.doesNotMatch(protectedText.split('\n').filter(line => !line.startsWith(PROTECTED_NOTE)).join('\n'), /Falsa alarma|falsas alarmas|Correctamente sin alerta|Precisión/)
  assert.equal(await page.$('[data-legend="FP"]'), null); assert.equal(await page.$('[data-legend="TN"]'), null)
  await page.waitForSelector('.pv-evolution svg')
  await scrollTo('.pv-controls'); await shot('desktop-donde')

  // Street base map: OSM attribution, offline notice, keyboard toggle and neighbourhood zoom.
  assert.match(await page.$eval('.pv-map .leaflet-control-attribution', e => e.textContent), /OpenStreetMap/)
  assert.match(await page.$eval('.pv-map-note', e => e.textContent), /no representan domicilios ni ubicaciones exactas/)
  assert.match(await page.$eval('[data-legend="records"]', e => e.textContent), /zona, no ubicación del caso/)
  assert.equal(await page.$('.pv-map .leaflet-marker-pane > *, .pv-map circle'), null, 'no markers or points inside radios')
  if (tilesOnline) {
    await page.waitForSelector('.pv-basetiles img.leaflet-tile-loaded')
    assert.equal(await page.$eval('.pv-basemap-offline', e => e.textContent), '')
    for (let i = 0; i < 4; i++) { await page.click('.pv-map-figure:first-child .leaflet-control-zoom-in'); await new Promise(r => setTimeout(r, 150)) }
    await new Promise(r => setTimeout(r, 2500)); await scrollTo('.pv-maps'); await shot('desktop-zoom-barrio')
    await page.click('.pv-map-figure figcaption button')
  } else {
    await page.waitForFunction(t => document.querySelector('.pv-basemap-offline')?.textContent === t, {}, OFFLINE_TEXT)
    await scrollTo('.pv-maps'); await shot('desktop-sin-conexion')
  }
  await page.focus('.pv-basemap-toggle input'); await page.keyboard.press('Space')
  await page.waitForFunction(() => !document.querySelector('.pv-basetiles') && !document.querySelector('.pv-basemap-toggle input').checked)
  await page.keyboard.press('Space'); await page.waitForSelector('.pv-basetiles')

  // Week navigation: arrows (network or cache), cache revisit and keyboard slider.
  await timed('next_week_until_rendered', () => page.click('[aria-label="Semana siguiente"]'), () => ready(defaultWeek))
  const second = await week()
  await timed('previous_week_cached_until_rendered', () => page.click('[aria-label="Semana anterior"]'), () => ready(second))
  await page.focus('#pv-week'); await page.keyboard.press('ArrowRight'); await ready(defaultWeek)
  await page.keyboard.press('ArrowLeft'); await ready(second)
  assert.equal(await week(), defaultWeek)

  // Empty and unavailable weeks: one explanation and a way back to activity.
  await timed('change_year_until_rendered', () => page.select('#pv-year', '2021'), () => ready(defaultWeek))
  if (!real) assert.match(await page.$eval('.pv-empty', e => e.textContent), /muy pocos registros por radio/)
  else await page.waitForSelector('.pv-empty, .pv-cards')
  assert.equal(await page.$$eval('.pv-empty', e => e.length) <= 1, true)
  if (await page.$('.pv-empty')) assert.equal(await page.$('.pv-map'), null, 'an empty week shows one explanation, not a map of protected cells')
  if (await page.$('.pv-empty')) { await scrollTo('.pv-controls'); await shot('desktop-sin-datos') }
  const in2021 = await week()
  await page.select('#pv-year', '2020'); await ready(in2021)
  assert.match(await page.$eval('.pv-empty', e => e.textContent), /Sin predicción/)
  const in2020 = await week()
  await page.waitForFunction(() => !document.querySelector('.pv-most-active')?.disabled)
  await page.click('.pv-most-active'); await ready(in2020)
  if (!real) assert.equal(await week(), defaultWeek)

  // ¿Cuántos?, Comparar and the radio panel.
  await press('view', 'quantity'); await page.waitForFunction(() => location.search.includes('vista=cuantos'))
  // The URL changes before React re-renders the model options: wait for the default quantity model.
  await page.waitForFunction(() => document.querySelector('[data-control="model"] select')?.value === 'residual_v2', { timeout: 10000 })
  await page.select('[data-control="model"] select', 'residual_h1'); await page.waitForFunction(() => location.search.includes('modelo=residual_h1'))
  assert.doesNotMatch(await page.$eval('.pv-model-rule', e => e.textContent), /10 radios/)
  await page.select('[data-control="model"] select', 'residual_v2'); await page.waitForFunction(() => location.search.includes('modelo=residual_v2'))
  assert.equal(await page.$('[data-legend="bin-0"]'), null, 'protected legend omits impossible ranges')
  await scrollTo('.pv-controls'); await shot('desktop-cuantos')
  await press('method', 'compare'); await page.waitForFunction(() => document.querySelectorAll('.pv-map').length === 2)
  await page.click('.pv-map-figure:first-child .leaflet-control-zoom-in')
  const synced = () => page.waitForFunction(() => { const maps = [...document.querySelectorAll('.pv-map')]; return maps.length === 2 && maps[0].dataset.btCamera === maps[1].dataset.btCamera })
  await synced(); await scrollTo('.pv-body'); await shot('desktop-comparar')
  // Regression: two changes in the same tick (before any re-render) must both reach the URL.
  await page.evaluate(() => { for (const [c, v] of [['method', 'ml'], ['view', 'presence']]) document.querySelector(`[data-control="${c}"] [data-value="${v}"]`).click() })
  await page.waitForFunction(() => location.search.includes('vista=donde') && location.search.includes('metodo=ml'))
  await openRadioWithKeyboard(); assert.match(page.url(), /radio=\d{9}/)
  await page.waitForFunction(() => /últimas|Últimas/.test(document.querySelector('.pv-spark figcaption')?.textContent || ''))
  assert.match(await page.$eval('.pv-panel', e => e.textContent), /Describe datos de entrada, no causas/)
  await scrollTo('.pv-body'); await shot('desktop-panel-radio')
  const sharedLink = page.url()
  await page.keyboard.press('Escape'); await page.waitForFunction(() => !document.querySelector('.pv-panel'))

  // Collapsed sections and technical metrics.
  await page.$$eval('.pv-section > summary', s => s.forEach(e => e.click()))
  assert.match(await text(), /Las cifras por año sólo se muestran en el modo privado/)
  await page.click('.pv-technical > summary'); await page.waitForSelector('.bt-ml-comparison')
  await page.$$eval('.pv-section', s => s.forEach(e => { e.open = false }))

  // Shared link restores the same state, always protected.
  await page.goto(sharedLink, { waitUntil: 'domcontentloaded' }); await ready()
  assert.equal(await week(), defaultWeek); await page.waitForSelector('.pv-panel')
  await assertProtectedMode()
  await page.click('.pv-close'); await page.waitForFunction(() => !document.querySelector('.pv-panel'))

  // Exact values only when dev was started with SIGARD_PRIVATE_VIEW=1; hidden otherwise.
  if (privateView) {
    // Private mode: warning, full legend; disclosure never written to the URL.
    await page.select('#bt-disclosure', 'private'); await page.waitForSelector('.pv-private-warning')
    await page.waitForFunction(() => document.querySelector('.pv')?.dataset.state === 'ready' && !document.querySelector('.pv-updating'))
    assert.match(await page.$eval('.pv-private-warning', e => e.textContent), /Modo privado: no proyectar ni compartir capturas/)
    await page.waitForSelector('[data-legend="FP"]'); assert.doesNotMatch(page.url(), /disclosure|privad/)
    // Private mode: recall@10 / onset@10 per year come from the server for the top-k candidate.
    await page.select('[data-control="model"] select', 'rf_v2_city_propensity'); await page.waitForFunction(() => location.search.includes('modelo=rf_v2_city_propensity'))
    await page.$eval('#pv-performance > summary', e => e.scrollIntoView()); await page.click('#pv-performance > summary')
    await page.waitForFunction(() => document.querySelector('#pv-performance').open)
    await page.waitForFunction(() => /Recall@10/.test(document.querySelector('#pv-performance')?.textContent || '') && /Onset@10/.test(document.querySelector('#pv-performance').textContent))
    assert.match(await page.$eval('#pv-performance', e => e.textContent), /Resultado similar al método de repetir la semana anterior/)
    await scrollTo('#pv-performance'); await shot('desktop-privado-rendimiento-v2')
    await page.$eval('#pv-performance', e => { e.open = false })
    await page.select('#bt-disclosure', 'presentation'); await page.waitForFunction(() => !document.querySelector('.pv-private-warning'))
    await ready()
  }

  // Mobile 390: no page-level horizontal scroll; bottom sheet panel.
  await page.setViewport({ width: 390, height: 844 }); await noHorizontalScroll()
  await page.evaluate(() => scrollTo(0, 0)); await scrollTo('.pv-controls'); await shot('movil-donde')
  if (tilesOnline) {
    for (let i = 0; i < 4; i++) { await page.click('.pv-map-figure:first-child .leaflet-control-zoom-in'); await new Promise(r => setTimeout(r, 150)) }
    await new Promise(r => setTimeout(r, 2500)); await scrollTo('.pv-maps'); await shot('movil-zoom-barrio')
    await page.click('.pv-map-figure figcaption button')
  } else { await scrollTo('.pv-maps'); await shot('movil-sin-conexion') }
  await press('view', 'quantity'); await scrollTo('.pv-body'); await shot('movil-cuantos'); await noHorizontalScroll()
  await press('method', 'compare'); await page.waitForFunction(() => document.querySelectorAll('.pv-map').length === 2); await scrollTo('.pv-body'); await shot('movil-comparar'); await noHorizontalScroll()
  await press('method', 'ml'); await press('view', 'presence'); await openRadioWithKeyboard()
  assert.equal(await page.$eval('.pv-panel', e => getComputedStyle(e).position), 'fixed'); await shot('movil-panel-radio')
  await page.click('.pv-close')
  await page.select('#pv-year', '2021'); await ready(defaultWeek)
  if (await page.$('.pv-empty')) { await scrollTo('.pv-controls'); await shot('movil-sin-datos') }
  await page.setViewport({ width: 820, height: 1100 }); await noHorizontalScroll()

  if (!real) {
    // Errors and retry; a failed week is not cached.
    await page.setViewport({ width: 1440, height: 1000 })
    fail = true; const before = await week(); await page.click('[aria-label="Semana siguiente"]'); await page.waitForSelector('.pv [role="alert"]')
    fail = false; await page.evaluate(() => [...document.querySelectorAll('.pv button')].find(b => b.textContent === 'Reintentar consulta').click()); await ready(before)
  } else {
    const measured = await page.evaluate(async () => {
      const operations = [['calendar', '/calendar'], ['geometry', '/geometry'], ['metadata', '/metadata'], ['week_protected', '/comparison?year=2024&week=12'], ['year_protected', '/history?start=2023-12-31&end=2024-12-22']]
      const results = [], token = sessionStorage.getItem('sigard_admin_token')
      for (const [operation, path] of operations) for (let sample = 0; sample < 3; sample++) {
        const start = performance.now(); const response = await fetch(`http://127.0.0.1:8767/api/v1/research/predictive${path}`, { headers: { 'X-Sigard-Research': 'local-read', Authorization: `Bearer ${token}` }, credentials: 'omit', cache: 'no-store' })
        if (!response.ok) throw new Error(`benchmark_status_${response.status}`)
        await response.json(); results.push({ operation, sample, seconds: (performance.now() - start) / 1000 })
      }
      return results
    }); timings.push(...measured)
  }
  // Expired session while using the viewer: no request, back to the login with a clear message, no console errors.
  await page.setViewport({ width: 1440, height: 1000 })
  const sent = requests.length
  await page.evaluate(token => sessionStorage.setItem('sigard_admin_token', token), fakeJwt(Math.floor(Date.now() / 1000) - 60))
  await page.select('#pv-year', '2024'); await loginNotice(SESSION_EXPIRED)
  assert.equal(requests.length, sent, 'an expired session sends no request')
  assert.equal(await page.evaluate(() => sessionStorage.getItem('sigard_admin_token')), null, 'the expired session is cleared')
  assert.equal(new URL(page.url()).pathname, PREDICTIVE_ROUTE)
  await shot('desktop-sesion-vencida')
  // The 60-minute expiry reached with the viewer open (no interaction): the timer returns to the login.
  if (!real) {
    await page.evaluate(token => sessionStorage.setItem('sigard_admin_token', token), fakeJwt(Math.floor(Date.now() / 1000) + 5, 'FIXTURE-EXPIRING'))
    await page.reload({ waitUntil: 'domcontentloaded' }); await ready()
    await loginNotice(SESSION_EXPIRED)
    const before = requests.length; await new Promise(r => setTimeout(r, 1500))
    assert.equal(requests.length, before, 'after the expiry by time nothing else is sent')
    assert.equal(await page.evaluate(() => sessionStorage.getItem('sigard_admin_token')), null)
  }
  // Revoked (or otherwise rejected) session: the server answers 401 and the page returns to the login.
  const revokedFrom = requests.length
  await page.evaluate(token => sessionStorage.setItem('sigard_admin_token', token), fakeJwt(Math.floor(Date.now() / 1000) + 600))
  const kept = new URL(page.url()).search
  await page.reload({ waitUntil: 'domcontentloaded' })
  await loginNotice(SESSION_EXPIRED); assert.ok(requests.length > revokedFrom, 'a not-yet-expired token is checked by the server')
  assert.equal(await page.evaluate(() => sessionStorage.getItem('sigard_admin_token')), null)
  // Logging in again restores the viewer on the same URL (state kept).
  await loginForm(); await ready()
  assert.equal(new URL(page.url()).search, kept)
  // Shared link with viewer state, opened without a session: login first, then exactly that state.
  const shared = '?anio=2024&se=12&vista=cuantos&metodo=comparar&modelo=residual_v2'
  await clearSession(); await page.goto(viewerUrl(shared), { waitUntil: 'domcontentloaded' })
  await loginNotice(SESSION_REQUIRED); assert.equal(new URL(page.url()).search, shared)
  await loginForm(); await ready()
  assert.equal(new URL(page.url()).pathname, PREDICTIVE_ROUTE)
  const sharedState = new URLSearchParams(new URL(page.url()).search)
  for (const [name, value] of new URLSearchParams(shared)) assert.equal(sharedState.get(name), value, `shared ${name}`)
  assert.equal(await page.$eval('[data-control="view"] [aria-pressed="true"]', e => e.dataset.value), 'quantity')
  assert.equal(await page.$eval('[data-control="method"] [aria-pressed="true"]', e => e.dataset.value), 'compare')
  await page.waitForFunction(() => document.querySelectorAll('.pv-map').length === 2)
  await shot('desktop-enlace-compartido')
  // Old /mapa viewer link with an administrator session: redirected to the viewer, state kept.
  const legacy = '?anio=2024&se=12&vista=cuantos&metodo=ml&capa=observados'
  await page.goto(`${origin}/mapa${legacy}`, { waitUntil: 'domcontentloaded' }); await ready()
  assert.equal(new URL(page.url()).pathname, PREDICTIVE_ROUTE)
  const legacyState = new URLSearchParams(new URL(page.url()).search)
  for (const [name, value] of new URLSearchParams(legacy)) assert.equal(legacyState.get(name), value, `legacy ${name}`)
  assert.equal(await page.$eval('[data-control="layer"] [aria-pressed="true"]', e => e.dataset.value), 'observed')
  // Without a session: /mapa is the public map, with a link to Administración that keeps the state.
  await clearSession(); const beforePublic = requests.length
  await page.goto(`${origin}/mapa${legacy}`, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => document.querySelector('.page-intro h1')?.textContent === 'Mapa público agregado')
  assert.equal(new URL(page.url()).pathname, '/mapa'); assert.equal(await page.$('.pv'), null); assert.equal(requests.length, beforePublic)
  assert.equal(await page.$eval('.predictive-moved a', e => e.textContent), 'El módulo predictivo está en Administración')
  await shot('desktop-mapa-publico-enlace')
  await page.click('.predictive-moved a'); await loginNotice(SESSION_REQUIRED)
  assert.equal(new URL(page.url()).pathname + new URL(page.url()).search, PREDICTIVE_ROUTE + legacy)
  // The menu link to the public map stays the public map in dev, also with a session (F4: the public
  // header is outside the Administración frame, so it is used from the public home).
  await loginForm(); await ready()
  await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded' })
  await page.click('.main-nav a[href="/mapa"]')
  await page.waitForFunction(() => document.querySelector('.page-intro h1')?.textContent === 'Mapa público agregado')
  assert.equal(await page.$('.pv'), null)
  // Access from Administración (same session).
  await page.goto(`${origin}/admin/reportes`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.admin-nav a[href="/admin/predictivo"]')
  await (await page.waitForSelector('.admin-nav a[href="/admin/predictivo"]')).click(); await ready()
  await shot('desktop-desde-administracion')
  assert.deepEqual(errors, [])
  // F7a: IBM Plex Sans/Mono come from the project itself; no font request leaves 127.0.0.1.
  const localFonts = await page.evaluate(async () => { await document.fonts.ready; return [...document.fonts].filter(f => f.status === 'loaded').map(f => `${f.family.replaceAll('"', '')} ${f.weight}`) })
  assert.ok(localFonts.includes('IBM Plex Sans 400') && localFonts.some(f => f.startsWith('IBM Plex Mono')), `fuentes locales cargadas: ${localFonts.join(', ')}`)
  assert.ok(external.every(o => !/fonts\.(googleapis|gstatic)\.com/.test(o)), 'sin pedidos a Google Fonts')
  if (!process.env.SIGARD_SKIP_PRODUCTION) {
    production = await preview({ root: frontendRoot, preview: { host: '127.0.0.1', port: 5174, strictPort: true } })
    // Count only once the dev viewer is idle: a background year load leaving as the page changes
    // would otherwise be counted as a request of the production build.
    await viewerIdle()
    const count = requests.length
    for (const path of ['/mapa?anio=2024&se=12', PREDICTIVE_ROUTE]) {
      await page.goto(`http://127.0.0.1:5174${path}`, { waitUntil: 'networkidle0' })
      assert.equal(await page.$('.historical-backtest'), null); assert.equal(requests.length, count)
    }
    assert.equal(await page.$('.admin-login'), null, 'production shows no viewer login')
  }
  const receipt = { status: 'passed', source: real ? 'private_real_aggregates_read_only' : 'generated_fictional_transport_only', browser_errors: errors,
    requests: requests.length, archived_calls: 0,
    tiles: tilesOnline ? 'osm_city_tiles_only' : 'blocked_offline', tile_requests_checked: tileRequests.length, external_requests_blocked: [...new Set(external)], no_private_api_in_production: !process.env.SIGARD_SKIP_PRODUCTION,
    no_training: true, fixtures_in_project_metrics: false, origin, local_fonts_loaded: localFonts, timings }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify({ ...receipt, timings: timings.filter(t => !t.sample).map(t => `${t.operation}: ${t.seconds.toFixed(2)} s`) }, null, 2))
} finally {
  await browser.close(); if (production) await new Promise(resolve => production.httpServer.close(resolve))
  if (environment) { await environment.stop(); await environment.closed; environment = undefined }
}
