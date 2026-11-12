// Complete final-module walkthrough. Default is fictional; --real reads local aggregates only.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { preview } from 'vite'
import { finalFixtureResponse } from '../security/predictive.fixture.mjs'

const require = createRequire(import.meta.url), puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const real = process.argv.includes('--real')
const output = resolve('data/interim/official/ml-integration-stage3-20261103-v1', process.argv.includes('--confirm') ? 'browser-confirmed' : 'browser', real ? 'real' : 'fictional')
await mkdir(output, { recursive: true })
const browser = await puppeteer.launch({ headless: true }); let production
const errors = [], external = [], requests = [], timings = []
try {
  const page = await browser.newPage(); page.setDefaultTimeout(25000)
  page.on('pageerror', e => errors.push(e.message))
  let fail = false, delayed = false
  await page.setRequestInterception(true)
  page.on('request', async r => {
    const u = new URL(r.url())
    if (!['http:', 'https:'].includes(u.protocol)) return r.continue()
    if (u.hostname !== '127.0.0.1' || !['5173', '5174', '8765'].includes(u.port)) { external.push(u.origin); return r.abort() }
    if (u.pathname.startsWith('/api/v1/research/')) {
      assert.ok(u.pathname.startsWith('/api/v1/research/predictive/'), 'no archived A/B or unprotected backtest calls')
      if (r.method() === 'OPTIONS') return r.respond({ status: 200, headers: { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173', 'Access-Control-Allow-Headers': 'X-Sigard-Research', 'Access-Control-Allow-Methods': 'GET' } })
      assert.equal(r.method(), 'GET'); requests.push(u.pathname)
      if (fail && u.pathname.endsWith('/comparison')) return r.respond({ status: 503, headers: { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173' }, body: '{}' })
      if (!real) {
        if (delayed && u.pathname.endsWith('/comparison')) await new Promise(resolve => setTimeout(resolve, 300))
        return r.respond({ status: 200, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173' }, body: JSON.stringify(finalFixtureResponse(u.href)) })
      }
    }
    return r.continue()
  })
  const ready = () => page.waitForSelector('.bt-territory-table tbody tr')
  await page.setViewport({ width: 1440, height: 1050 })
  const started = performance.now(); await page.goto('http://127.0.0.1:5173/mapa', { waitUntil: 'networkidle0' }); await ready()
  timings.push({ operation: 'initial_module_until_week_rendered', seconds: (performance.now() - started) / 1000 })
  assert.equal(await page.$('.research-mode'), null)
  assert.equal(await page.$eval('#bt-disclosure', e => e.value), 'presentation')
  await page.select('#bt-year', '2020'); await ready()
  assert.equal(await page.$$eval('#bt-week option', e => e.length), 53)
  await page.select('#bt-week', '2020-12-27'); await ready()
  assert.match(await page.$eval('.bt-unavailable', e => e.textContent), /Predicción no disponible/)
  await page.select('#bt-year', '2021'); await ready()
  if (!real) assert.match(await page.$eval('.bt-ml-comparison', e => e.textContent), /Predicción ML no disponible/)
  await page.select('#bt-source', 'reference'); await page.select('#bt-source', 'ml')
  assert.match(await page.$eval('.bt-period', e => e.textContent), /2020-12-27 a 2021-01-02/)
  await page.select('#bt-year', '2022'); await ready()
  await page.select('#bt-year', '2024'); await ready()
  const selected = performance.now(); await page.select('#bt-week', '2024-03-17'); await ready()
  timings.push({ operation: 'select_week_until_comparison_rendered', seconds: (performance.now() - selected) / 1000 })
  await page.waitForSelector('.bt-chart svg')
  assert.match(await page.$eval('.bt-ml-comparison', e => e.textContent), /rf_A_epi_climate/)
  assert.match(await page.$eval('.bt-climate', e => e.textContent), /°C/)
  const shots = async name => { await page.evaluate(() => scrollTo(0, 0)); await page.screenshot({ path: resolve(output, name), fullPage: true }) }
  await shots('desktop-presence.private.png'); await page.select('#bt-view', 'quantity'); await shots('desktop-quantity.private.png')
  await page.click('.bt-dual-maps figure:first-child .leaflet-control-zoom-in')
  const synced = () => page.waitForFunction(() => { const maps = [...document.querySelectorAll('.bt-map')]; return maps.length === 2 && maps[0].dataset.btCamera === maps[1].dataset.btCamera })
  await synced(); await page.setViewport({ width: 390, height: 844 }); await synced(); await shots('mobile-quantity.private.png')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
  await page.select('#bt-view', 'presence'); await shots('mobile-presence.private.png')
  await page.select('#bt-disclosure', 'private'); await ready()
  assert.match(await page.$eval('.bt-disclosure', e => e.textContent), /No proyectar, publicar ni compartir/)
  const first = await page.$eval('#bt-radio option:nth-child(2)', e => e.value)
  await page.select('#bt-radio', first)
  assert.equal(await page.$$eval('.bt-territory-table tbody tr', e => e.length), 1)
  await page.select('#bt-radio', '')
  await page.select('#bt-week', '2024-12-22'); await ready()
  assert.equal(await page.$eval('.bt-week-summary .bt-summary-values dd', e => e.textContent), '0')
  await page.select('#bt-year', '2025'); await ready()
  assert.match(await page.$eval('.bt-unavailable', e => e.textContent), /Fuera de cobertura/)
  if (!real) {
    fail = true; await page.select('#bt-year', '2023'); await page.waitForSelector('.historical-backtest [role="alert"]')
    assert.equal(await page.$('.bt-territory-table'), null); fail = false
    await page.evaluate(() => [...document.querySelectorAll('.historical-backtest button')].find(b => b.textContent === 'Reintentar consulta').click()); await ready()
    delayed = true; await page.select('#bt-year', '2022'); assert.equal(await page.$('.bt-territory-table'), null)
    await page.select('#bt-year', '2024'); await ready(); assert.match(await page.$eval('.bt-period', e => e.textContent), /SE 1\/2024/); delayed = false
  } else {
    // Sequential loopback fetch+JSON timings, no response bodies saved.
    const measured = await page.evaluate(async () => {
      const operations = [ ['week_private', '/comparison?year=2024&week=12&disclosure=private'], ['week_protected', '/comparison?year=2024&week=12'],
        ['year_private', '/history?start=2023-12-31&end=2024-12-22&disclosure=private'], ['year_protected', '/history?start=2023-12-31&end=2024-12-22'],
        ['full_calendar_private', '/history?start=2019-12-29&end=2026-12-27&disclosure=private'],
        ['full_calendar_protected', '/history?start=2019-12-29&end=2026-12-27'] ]
      const results = []
      for (const [operation, path] of operations) for (let sample = 0; sample < 5; sample++) {
        const start = performance.now(); const response = await fetch(`http://127.0.0.1:8765/api/v1/research/predictive${path}`, { headers: { 'X-Sigard-Research': 'local-read' }, credentials: 'omit', cache: 'no-store' })
        if (!response.ok) throw new Error(`benchmark_status_${response.status}`)
        await response.json(); results.push({ operation, sample, seconds: (performance.now() - start) / 1000 })
      }
      return results
    }); timings.push(...measured)
  }
  assert.deepEqual(errors, [])
  production = await preview({ root: resolve('frontend'), preview: { host: '127.0.0.1', port: 5174, strictPort: true } })
  const count = requests.length; await page.goto('http://127.0.0.1:5174/mapa', { waitUntil: 'networkidle0' })
  assert.equal(await page.$('.historical-backtest'), null); assert.equal(requests.length, count)
  const receipt = { status: 'passed', source: real ? 'private_real_aggregates_read_only' : 'generated_fictional_transport_only', browser_errors: errors,
    requests: requests.length, archived_calls: 0, external_requests_blocked: [...new Set(external)], no_private_api_in_production: true,
    no_training: true, fixtures_in_project_metrics: false, timings }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify({ ...receipt, timings: `${timings.length} measurements in private receipt` }))
} finally { await browser.close(); if (production) await new Promise(resolve => production.httpServer.close(resolve)) }
