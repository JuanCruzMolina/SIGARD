// End-to-end offline UI checks with generated fictional polygons/counts only.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const require = createRequire(import.meta.url)
let puppeteer
try { puppeteer = require('puppeteer') } catch {
  const path = process.env.SIGARD_BROWSER_MODULE
  if (!path) throw new Error('Use the existing Puppeteer installation via SIGARD_BROWSER_MODULE; no dependency installation required.')
  puppeteer = require(path)
}
const out = fileURLToPath(new URL('../.tmp/predictive-viewer', import.meta.url))
const ids = Array.from({ length: 256 }, (_, i) => `fictional_${String(i).padStart(3, '0')}`)
const geometry = { type: 'FeatureCollection', features: ids.map((id, i) => {
  const x = i % 16 * .01, y = Math.floor(i / 16) * .01
  return { type: 'Feature', properties: { radio_id: id }, geometry: { type: 'Polygon', coordinates: [[[x,y],[x+.009,y],[x+.009,y+.009],[x,y+.009],[x,y]]] } }
}) }
const queries = Object.fromEntries([1, 2, 4].map(h => [String(h), ['2024-04-07', '2024-04-14'].map(target => ({
  target_week: target, target_end: target === '2024-04-07' ? '2024-04-13' : '2024-04-20', target_year: 2024, target_week_number: 15,
  origin_week: '2024-03-10', information_cutoff: '2024-03-16', model_version: 'fictional_v2', horizon_weeks: h,
  selected_method: 'lag_1_or_training_mean', eligible_radios: 255, radios_without_estimate: 1, radios_with_incomplete_predictors: 55,
  expected_eligible_total: ids.slice(0, -1).reduce((sum, _id, i) => sum + i % 4 * h, 0), expected_territorial_total: null,
  radios: ids.map((radio_id, i) => ({ radio_id, expected_count: i === 255 ? null : i % 4 * h,
    estimate_status: i === 255 ? 'insufficient_data' : i >= 200 ? 'available_with_historical_mean_fallback' : 'available',
    available_features: i >= 200 ? 8 : 21, missing_features: i >= 200 ? ['cases_lag_1'] : [],
    observed_snapshot_count: i < 10 ? 1 : null, observed_quality_state: i < 10 ? 'recorded_positive' : 'unknown_pending' }))
}))]))
const payload = { schema: 'sigard-private-predictive-viewer/1', geometry, queries, initial_date: '2024-04-07', initial_horizon: 1,
  comparison: [{ id: 'fictional', label: 'Comparación totalmente ficticia', scope: 'Fixture generada; no son métricas sanitarias', n: 5, mae: 1, rmse: 2, mean_bias: -1 }] }
const file = resolve(out, 'fictional-viewer.html')
await writeFile(file, (await readFile(resolve(out, 'viewer.html'), 'utf8')).replace('__SIGARD_PRIVATE_PAYLOAD__', JSON.stringify(payload)))
const browser = await puppeteer.launch({ headless: true })
const report = { checks: [], errors: [], networkRequests: [], viewports: [], dataKind: 'fictional_only' }
try {
  const page = await browser.newPage()
  page.on('pageerror', error => report.errors.push(error.message))
  await page.setRequestInterception(true)
  page.on('request', request => {
    const url = request.url()
    if (url === pathToFileURL(file).href || /^(data:|blob:)/.test(url)) return request.continue()
    report.networkRequests.push(url)
    return request.abort()
  })
  await page.setViewport({ width: 1440, height: 1050 })
  await page.goto(pathToFileURL(file).href, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.leaflet-interactive')
  assert.equal(await page.$$eval('.leaflet-interactive', nodes => nodes.length), 256)
  assert.ok((await page.$eval('.presence-notice', node => node.textContent)).includes('en evaluación'))
  assert.equal(await page.$$eval('.map-side-panel select option', nodes => nodes.length), 257)
  const selector = '.map-side-panel select'
  await page.select(selector, ids[201])
  await page.waitForSelector('[data-testid="radio-estimate"]')
  assert.ok((await page.$eval('.radio-details', node => node.textContent)).includes('respaldo de media histórica'))
  await page.select(selector, ids[255])
  assert.ok((await page.$eval('.radio-details', node => node.textContent)).includes('Información insuficiente'))
  for (const h of ['1','2','4']) {
    await page.select('#prediction-horizon', h)
    assert.equal(await page.$eval('#territorial-total', node => node.textContent), `${new Intl.NumberFormat('es-AR').format(381 * Number(h))} registros`)
    await page.select('#prediction-week', '2024-04-14')
    assert.ok((await page.$eval('.query-summary h2', node => node.textContent)).includes('2024-04-14'))
  }
  report.checks.push('all horizons/date selection, 256 polygons, total, partial predictors and unavailable radio')
  await page.$eval('#prediction-date', node => { const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; setter.call(node, '2026-10-26'); node.dispatchEvent(new Event('input', { bubbles:true })); node.dispatchEvent(new Event('change', { bubbles:true })) })
  await page.waitForSelector('.unavailable-query')
  assert.equal(await page.$('#territorial-total'), null)
  assert.equal(await page.$$eval('.leaflet-interactive', nodes => nodes.length), 0)
  assert.equal(await page.$eval(selector, node => node.disabled), true)
  report.checks.push('2026 suppresses stale counts and map, with insufficient data status')
  await page.select('#prediction-week', '2024-04-07')
  assert.equal(await page.$$eval(`${selector} option[value="fictional_excluded"]`, nodes => nodes.length), 0)
  await page.click('.values-table summary')
  await page.click('.incomplete-filter input')
  assert.equal(await page.$$eval('.values-table tbody tr', nodes => nodes.length), 56)
  for (const width of [1440, 390]) {
    await page.setViewport({ width, height: 1050 })
    await page.select(selector, ids[201])
    await page.$eval('.values-table', node => { node.open = false })
    const layout = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth > innerWidth,
      controlsFit: [...document.querySelectorAll('.viewer-controls input,.viewer-controls select')].every(node => node.getBoundingClientRect().right <= innerWidth),
      legendBelowMap: document.querySelector('.count-legend').getBoundingClientRect().top >= document.querySelector('.leaflet-map').getBoundingClientRect().bottom - 1 }))
    assert.equal(layout.overflow, false); assert.equal(layout.controlsFit, true); assert.equal(layout.legendBelowMap, true)
    report.viewports.push({ width, ...layout })
    await page.screenshot({ path: resolve(out, `fictional-${width}.png`), fullPage: true })
  }
  report.checks.push('keyboard selectors, excluded code absent, insufficiency filter, desktop/mobile layout')
  assert.deepEqual(report.networkRequests, [])
  assert.deepEqual(report.errors, [])
  console.log(JSON.stringify(report))
  await writeFile(resolve(out, 'browser-report.json'), JSON.stringify(report, null, 2))
} catch (error) {
  const pages = await browser.pages()
  console.error(JSON.stringify({ ...report, pageText: await pages.at(-1).evaluate(() => document.body.textContent.slice(0, 2000)) }))
  throw error
} finally { await browser.close() }
