// Complete predictive-module walkthrough. Default is fictional; --real reads local aggregates only.
// Requires the frontend on 127.0.0.1:5173 (npm run dev) and a previous `npm run build` for the production check.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { preview } from 'vite'
import { finalFixtureResponse } from '../security/predictive.fixture.mjs'

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
const output = resolve(frontendRoot, '..', 'data/interim/official/ux-predictive-redesign-20261112', process.env.SIGARD_SHOTS_LABEL || 'despues', real ? 'real' : 'fictional', tilesOnline ? 'con-calles' : 'sin-conexion')
await mkdir(output, { recursive: true })
const browser = await puppeteer.launch({ headless: true }); let production
const errors = [], external = [], requests = [], timings = [], tileRequests = []
const PROTECTED_NOTE = 'En modo protegido sólo se muestran radios con 5 o más registros'
try {
  const page = await browser.newPage(); page.setDefaultTimeout(30000)
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()) })
  let fail = false
  await page.setRequestInterception(true)
  page.on('request', async r => {
    const u = new URL(r.url())
    if (!['http:', 'https:'].includes(u.protocol)) return r.continue()
    if (/^[abc]\.tile\.openstreetmap\.org$/.test(u.hostname)) {
      const match = /^\/(\d+)\/(\d+)\/(\d+)\.png$/.exec(u.pathname), [z, x, y] = (match || []).slice(1).map(Number)
      assert.ok(match && u.protocol === 'https:' && !u.search && !u.hash && !u.username, `tile request carries only tile coordinates: ${u.href}`)
      assert.ok(z >= 11 && z <= 17, 'tile zoom within the city range')
      assert.ok(tileLat(y + 1, z) <= CITY.north && tileLat(y, z) >= CITY.south && tileLng(x + 1, z) >= CITY.west && tileLng(x, z) <= CITY.east, `tile within the map area: ${z}/${x}/${y}`)
      assert.ok(!r.headers().referer, 'no referrer (page URL, week or radio) sent to the tile server')
      assert.equal(r.method(), 'GET'); assert.equal(r.postData(), undefined)
      tileRequests.push(`${z}/${x}/${y}`)
      return tilesOnline ? r.continue() : r.abort()
    }
    if (u.hostname !== '127.0.0.1' || !['5173', '5174', '8765'].includes(u.port)) { external.push(u.origin); return r.abort() }
    if (u.pathname.startsWith('/api/v1/research/')) {
      assert.ok(u.pathname.startsWith('/api/v1/research/predictive/'), 'no archived A/B or unprotected backtest calls')
      if (r.method() === 'OPTIONS') return r.respond({ status: 200, headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Headers': 'X-Sigard-Research', 'Access-Control-Allow-Methods': 'GET' } })
      assert.equal(r.method(), 'GET'); requests.push(`${u.pathname}${u.search}`)
      if (fail && u.pathname.endsWith('/comparison')) return r.respond({ status: 503, headers: { 'Access-Control-Allow-Origin': origin }, body: '{}' })
      if (!real) return r.respond({ status: 200, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': origin }, body: JSON.stringify(finalFixtureResponse(u.href)) })
    }
    return r.continue()
  })
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
  await timed('cold_start_until_default_week_rendered', () => page.goto(`${origin}/mapa`, { waitUntil: 'domcontentloaded' }), () => ready())
  const defaultWeek = await week()
  if (!real) assert.equal(defaultWeek, '2024-04-07', 'fictional default is the week with most disclosable radios')
  assert.ok(timings[0].seconds < 5, `cold start under 5 s (${timings[0].seconds.toFixed(2)} s)`)
  // Model selector built from metadata: corrective v2 by default, v1 candidates still available.
  assert.equal(await page.$eval('[data-control="model"] select', e => e.value), 'rf_v2_city_propensity')
  assert.deepEqual(await page.$$eval('[data-control="model"] option', o => o.map(e => e.value)), ['rf_A_epi_climate', 'rf_v2_city_propensity'])
  assert.match(await page.$eval('.pv-model-rule', e => e.textContent), /Marca los 10 radios con mayor prioridad cada semana/)
  assert.match(page.url(), /anio=\d{4}&se=\d+/)
  assert.equal(await page.$eval('#bt-disclosure', e => e.value), 'presentation')
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
  assert.equal(await page.$eval('[data-control="model"] select', e => e.value), 'residual_v2')
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
  assert.equal(await page.$eval('#bt-disclosure', e => e.value), 'presentation')
  await page.click('.pv-close'); await page.waitForFunction(() => !document.querySelector('.pv-panel'))

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
      const results = []
      for (const [operation, path] of operations) for (let sample = 0; sample < 3; sample++) {
        const start = performance.now(); const response = await fetch(`http://127.0.0.1:8765/api/v1/research/predictive${path}`, { headers: { 'X-Sigard-Research': 'local-read' }, credentials: 'omit', cache: 'no-store' })
        if (!response.ok) throw new Error(`benchmark_status_${response.status}`)
        await response.json(); results.push({ operation, sample, seconds: (performance.now() - start) / 1000 })
      }
      return results
    }); timings.push(...measured)
  }
  assert.deepEqual(errors, [])
  if (!process.env.SIGARD_SKIP_PRODUCTION) {
    production = await preview({ root: frontendRoot, preview: { host: '127.0.0.1', port: 5174, strictPort: true } })
    const count = requests.length; await page.goto('http://127.0.0.1:5174/mapa', { waitUntil: 'networkidle0' })
    assert.equal(await page.$('.historical-backtest'), null); assert.equal(requests.length, count)
  }
  const receipt = { status: 'passed', source: real ? 'private_real_aggregates_read_only' : 'generated_fictional_transport_only', browser_errors: errors,
    requests: requests.length, archived_calls: 0,
    tiles: tilesOnline ? 'osm_city_tiles_only' : 'blocked_offline', tile_requests_checked: tileRequests.length, external_requests_blocked: [...new Set(external)], no_private_api_in_production: !process.env.SIGARD_SKIP_PRODUCTION,
    no_training: true, fixtures_in_project_metrics: false, origin, timings }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify({ ...receipt, timings: timings.filter(t => !t.sample).map(t => `${t.operation}: ${t.seconds.toFixed(2)} s`) }, null, 2))
} finally { await browser.close(); if (production) await new Promise(resolve => production.httpServer.close(resolve)) }
