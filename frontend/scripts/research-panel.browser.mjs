// Real local read-only walkthrough, then a separate in-memory fictional UI harness.
// Requires the existing dev coordinator. Never writes scores, fixtures or API bodies.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { preview } from 'vite'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const origin = 'http://127.0.0.1:5173'
const output = resolve('frontend/.tmp/research-panel')
const schema = 'sigard-retrospective-spatial-score/1'
const days = [...Array(8)].map((_, i) => 7 + i * 7).concat([...Array(8)].map((_, i) => 70 + i * 7), [...Array(4)].map((_, i) => 133 + i * 7))
const weeks = days.map((day, i) => ({ target_week_start: new Date(Date.UTC(2024, 0, day)).toISOString().slice(0, 10), target_week_end: new Date(Date.UTC(2024, 0, day + 6)).toISOString().slice(0, 10), target_epidemiological_year: 2024, target_epidemiological_week: Math.floor(day / 7) + 1, evaluation_partition: i < 8 ? 'train' : i < 16 ? 'validation' : 'test' }))
const models = ['A', 'B'].map(id => ({ model_id: id, experiment_id: id === 'A' ? 'spatial_rf_05c_v1' : 'spatial_rf_B_05f_v1', training_version: id === 'A' ? 'official-spatial-rf-research-0.5c.0' : 'official-spatial-rf-B-research-0.5f.0', weeks }))
const ids = Array.from({ length: 263 }, (_, i) => `fictional-${String(i).padStart(3, '0')}`)
const geometry = { type: 'FeatureCollection', features: ids.map((id, i) => {
  const x = (i % 20) * .01, y = Math.floor(i / 20) * .01
  return { type: 'Feature', properties: { radio_id: id }, geometry: { type: 'Polygon', coordinates: [[[x, y], [x + .009, y], [x + .009, y + .009], [x, y + .009], [x, y]]] } }
}) }
function scores(id, week, radio) {
  const meta = weeks.find(w => w.target_week_start === week)
  const model = models.find(m => m.model_id === id)
  return { schema_version: schema, model_id: id, experiment_id: model.experiment_id, training_version: model.training_version, ...meta,
    territory_version: 'capital-census-2022-public-v1', calendar_version: 'ar-snvs-2020-2026-v1', data_kind: 'official_experimental_retrospective', score_semantics: 'raw_class_1_score_uncalibrated', retrospective: true, operational_use_authorized: false, publication_authorized: false, coverage_verified: false, previously_examined: true, coverage_scenario: 'spatial_assumed_2024_v1', interpretation_limitations: Array(10).fill('fictional'),
    rows: (radio ? [radio] : ids).map((radio_censal) => {
      const index = ids.indexOf(radio_censal)
      const score = index === 0 ? (id === 'A' ? .2 : .7) : index === 1 ? (id === 'A' ? .7 : .2) : index === 2 ? 0 : index === 3 && id === 'B' ? null : .3
      return { radio_censal, experimental_score: score, score_status: score === null ? 'not_computed' : 'available', score_unavailable_reason: score === null ? 'frozen_score_missing' : null, data_availability: { prediction_as_of: null, operational_availability: 'not_accredited', known_lag_count: id === 'A' ? null : 3 } }
    }) }
}
const comparison = (week, radio) => ({ schema_version: schema, target_week_start: week, radio_censal: radio, comparable: radio !== ids[3], results: ['A', 'B'].map(id => scores(id, week, radio)) })
const metrics = { precision: .2, recall: .3, f1: .24, average_precision_pr_auc: .4, roc_auc: .6, brier: .3 }
const evaluation = { schema_version: 'sigard-retrospective-spatial-evaluation/1', calendar_version: 'ar-snvs-2020-2026-v1', coverage_scenario: 'spatial_assumed_2024_v1', coverage_verified: false, retrospective: true, previously_examined: true, operational_use_authorized: false, publication_authorized: false, evaluation_source: 'frozen_comparative_evaluation', threshold: .5, interpretation_limitations: Array(10).fill('fictional'), partitions: ['train', 'validation', 'test'].map(partition => {
  const subset = weeks.filter(w => w.evaluation_partition === partition)
  return { partition, target_week_start: subset[0].target_week_start, target_week_end: subset.at(-1).target_week_end, week_count: subset.length, evaluated_radio_weeks: subset.length * 263, models: models.map(({ weeks: _weeks, ...m }) => ({ ...m, metrics: m.model_id === 'A' ? metrics : { ...metrics, recall: .5, brier: .4 } })) }
}) }
const browser = await puppeteer.launch({ headless: true })
const report = { checks: [], pageErrors: [], viewports: [], privateResultsSaved: false }
let production
const checkpoint = name => { report.checks.push(name); console.log(name) }
try {
  await mkdir(output, { recursive: true })
  const page = await browser.newPage()
  page.setDefaultTimeout(12000)
  page.on('pageerror', e => report.pageErrors.push(e.message))
  await page.setRequestInterception(true)
  page.on('request', r => {
    const u = new URL(r.url())
    if (u.hostname === '127.0.0.1' && ['5173', '5174', '8765'].includes(u.port) || ['data:', 'blob:'].includes(u.protocol)) return r.continue()
    return r.abort()
  })
  await page.setViewport({ width: 1440, height: 1000 })
  await page.goto(origin, { waitUntil: 'networkidle0' })
  await page.waitForFunction(() => document.querySelector('.research-availability')?.textContent.includes('radios con'))
  assert.equal(new URL(page.url()).pathname, '/mapa')
  assert.equal(await page.$$eval('#research-model option', o => o.length), 3)
  await page.waitForSelector('.metric-comparison tbody tr')
  const radio = await page.$eval('#research-radio', e => e.options[1].value)
  await page.select('#research-radio', radio)
  await page.waitForSelector('.radio-difference')
  const week = await page.$eval('#research-week', e => e.value)
  for (const mode of ['B', 'difference', 'A']) {
    await page.select('#research-model', mode)
    assert.equal(await page.$eval('#research-week', e => e.value), week)
    assert.equal(await page.$eval('#research-radio', e => e.value), radio)
    assert.equal(await page.$$eval('.leaflet-container', e => e.length), 1)
  }
  await page.evaluate(() => [...document.querySelectorAll('button')].find(b => b.textContent === 'Ver evolución temporal').click())
  await page.waitForSelector('.radio-timeline svg')
  for (const partition of ['train', 'validation', 'test']) await page.select('#analysis-partition', partition)
  checkpoint('Real local app: default A/B entry, 3 views, same week/radio, history and 6 metrics/3 partitions')
  for (const width of [1440, 390]) {
    await page.setViewport({ width, height: 1000 })
    const layout = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth > innerWidth,
      controlsFit: [...document.querySelectorAll('.research-controls select')].every(e => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth }),
      legendBelowMap: document.querySelector('.research-legend').getBoundingClientRect().top >= document.querySelector('.leaflet-container').getBoundingClientRect().bottom - 1,
    }))
    assert.equal(layout.overflow, false); assert.equal(layout.controlsFit, true); assert.equal(layout.legendBelowMap, true)
    report.viewports.push({ realApp: true, width, ...layout })
  }
  checkpoint('Real app shell: 1440/390 px, controls within viewport, no horizontal overflow or overlapping legend')
  await page.click('.research-mode button:first-child')
  await page.waitForSelector('#cutoff-week')
  await page.click('a[href="/dashboard"]')
  await page.waitForFunction(() => location.pathname === '/dashboard')
  checkpoint('Synthetic MVP and original dashboard remain reachable')

  // This tab has wholly fictional polygons and identifiers, unrelated to official geography.
  const fixture = await browser.newPage()
  fixture.setDefaultTimeout(12000)
  fixture.on('pageerror', e => report.pageErrors.push(e.message))
  let failB = false, failCatalog = false, failEvaluation = false, failHistory = false, delayWeek = '', delayedHistory = '', pending = []
  await fixture.setRequestInterception(true)
  const respond = (r, body, status = 200) => r.respond({ status, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Headers': 'X-Sigard-Research', 'Cache-Control': 'no-store' }, body: JSON.stringify(body) })
  fixture.on('request', async r => {
    const u = new URL(r.url())
    if (u.pathname === '/__research_fixture__') return r.respond({ contentType: 'text/html', body: '<html><body><div class="app-shell"><main><div id="root" class="content-wrap"></div></main></div></body></html>' })
    if (u.port === '8765') {
      if (r.method() === 'OPTIONS') return respond(r, {})
      const path = u.pathname.replace('/api/v1/research/spatial', '')
      if (path === '/models') return respond(r, { schema_version: schema, models }, failCatalog ? 503 : 200)
      if (path === '/evaluation') return respond(r, evaluation, failEvaluation ? 404 : 200)
      if (path.startsWith('/history/')) {
        const radio = decodeURIComponent(path.split('/').at(-1))
        if (radio === delayedHistory) { pending.push(() => respond(r, { schema_version: schema, radio_censal: radio, comparisons: weeks.map(w => comparison(w.target_week_start, radio)) }).catch(() => {})); return }
        return respond(r, { schema_version: schema, radio_censal: radio, comparisons: weeks.map(w => comparison(w.target_week_start, radio)) }, failHistory ? 503 : 200)
      }
      const match = path.match(/^\/models\/([AB])\/scores\/(.+)$/)
      if (match) {
        if (match[2] === delayWeek) { pending.push(() => respond(r, scores(match[1], match[2])).catch(() => {})); return }
        return respond(r, scores(match[1], match[2]), failB && match[1] === 'B' ? 503 : 200)
      }
      return respond(r, {}, 404)
    }
    if (u.hostname === '127.0.0.1' && u.port === '5173' || ['data:', 'blob:'].includes(u.protocol)) return r.continue()
    return r.abort()
  })
  const mount = async () => {
    await fixture.goto(origin + '/__research_fixture__', { waitUntil: 'networkidle0' })
    await fixture.evaluate(async geometry => {
      const RefreshRuntime = (await import('/@react-refresh')).default
      RefreshRuntime.injectIntoGlobalHook(window)
      window.$RefreshReg$ = () => {}
      window.$RefreshSig$ = () => type => type
      window.__vite_plugin_react_preamble_installed__ = true
      const React = (await import('/node_modules/.vite/deps/react.js')).default
      const { createRoot } = (await import('/node_modules/.vite/deps/react-dom_client.js')).default
      const Panel = (await import('/src/components/ExperimentalSpatial.jsx')).default
      await import('/src/index.css'); await import('/src/App.css')
      createRoot(document.querySelector('#root')).render(React.createElement(Panel, { geometry }))
    }, geometry)
  }
  const ready = () => fixture.waitForFunction(() => document.querySelector('.research-availability')?.textContent.includes('radios con'))
  await fixture.setViewport({ width: 1440, height: 1000 })
  await mount(); await ready()
  await fixture.select('#research-model', 'difference')
  for (const [index, expected] of [[0, '+0,500000'], [1, '-0,500000'], [2, '0,000000'], [3, 'No disponible']]) {
    await fixture.select('#research-radio', ids[index])
    assert.equal(await fixture.$eval('.radio-difference strong', e => e.textContent), expected)
  }
  const mapColors = await fixture.$$eval('.leaflet-interactive', e => e.slice(0, 4).map(x => x.getAttribute('fill')))
  assert.equal(new Set(mapColors).size, 4)
  await fixture.select('#research-radio', ids[1])
  await fixture.click('.leaflet-control-zoom-out')
  await fixture.click('.leaflet-interactive')
  assert.equal(await fixture.$eval('#research-radio', e => e.value), ids[0])
  await fixture.focus('#research-radio'); await fixture.keyboard.press('ArrowDown'); await fixture.keyboard.press('Enter')
  assert.equal(await fixture.$eval('#research-radio', e => e.value), ids[1])
  await fixture.focus('.leaflet-container'); await fixture.keyboard.press('ArrowRight')
  await fixture.focus('.map-reset'); await fixture.keyboard.press('Enter')
  checkpoint('Fictional UI: positive/negative/zero/missing difference, divergent colors, map/text selection and keyboard')
  delayWeek = weeks[1].target_week_start
  await fixture.select('#research-week', delayWeek)
  await fixture.waitForFunction(() => document.querySelector('.research-availability [role="status"]'))
  await fixture.select('#research-model', 'B'); await fixture.select('#research-radio', ids[2])
  await fixture.select('#research-week', weeks[2].target_week_start); await ready()
  await Promise.all(pending.splice(0).map(fn => fn())); delayWeek = ''
  assert.equal(await fixture.$eval('#research-week', e => e.value), weeks[2].target_week_start)
  assert.ok((await fixture.$eval('.radio-target', e => e.textContent)).includes(weeks[2].target_week_start))
  checkpoint('Fictional UI: rapid week/model/radio changes discard late weekly results')
  failB = true
  await fixture.select('#research-week', weeks[3].target_week_start); await ready()
  await fixture.waitForSelector('.research-error [role="alert"]')
  assert.equal(await fixture.$eval('.radio-difference strong', e => e.textContent), 'No disponible')
  failB = false; await fixture.click('.research-error button'); await ready()
  assert.equal(await fixture.$('.research-error'), null)
  delayedHistory = ids[0]
  await fixture.select('#research-radio', ids[0])
  await fixture.evaluate(() => [...document.querySelectorAll('button')].find(b => b.textContent === 'Ver evolución temporal').click())
  await fixture.select('#research-radio', ids[1]); await fixture.waitForSelector('.radio-timeline svg')
  await Promise.all(pending.splice(0).map(fn => fn())); delayedHistory = ''
  assert.ok((await fixture.$eval('.radio-timeline svg', e => e.getAttribute('aria-label'))).includes(ids[1]))
  failHistory = true; await fixture.select('#research-radio', ids[3])
  await fixture.waitForSelector('.analysis-temporal [role="alert"]')
  failHistory = false; await fixture.click('.analysis-temporal button'); await fixture.waitForSelector('.radio-timeline svg')
  checkpoint('Fictional UI: partial score API error/retry, late history ignored and history error/retry')
  for (const width of [1440, 390]) {
    await fixture.setViewport({ width, height: 1000 })
    await fixture.select('#research-model', 'difference')
    await fixture.$eval('.analysis-values', e => e.open = true)
    await fixture.$eval('.research-guide', e => e.open = true)
    const layout = await fixture.evaluate(() => {
      const map = document.querySelector('.leaflet-container').getBoundingClientRect()
      const legend = document.querySelector('.research-legend').getBoundingClientRect()
      const controls = [...document.querySelectorAll('.research-controls select')].map(e => e.getBoundingClientRect())
      return { overflow: document.documentElement.scrollWidth > innerWidth, legendBelowMap: legend.top >= map.bottom - 1, controlsFit: controls.every(r => r.left >= 0 && r.right <= innerWidth), mapHeight: map.height }
    })
    assert.equal(layout.overflow, false); assert.equal(layout.legendBelowMap, true); assert.equal(layout.controlsFit, true)
    assert.ok(layout.mapHeight >= 350)
    report.viewports.push({ width, ...layout })
    await fixture.screenshot({ path: resolve(output, `fictional-panel-${width}.png`), fullPage: true })
  }
  checkpoint('Fictional UI: desktop 1440/mobile 390, full panel, scrollable tables/chart, no horizontal overflow or legend overlap')
  failCatalog = true; await mount(); await fixture.waitForSelector('.research-controls [role="alert"]')
  failCatalog = false; await fixture.click('.research-controls button'); await ready()
  failEvaluation = true; await mount(); await fixture.waitForSelector('.experimental-analysis [role="alert"]')
  failEvaluation = false; await fixture.click('.experimental-analysis button'); await fixture.waitForSelector('.metric-comparison')
  checkpoint('Fictional UI: catalogue failure and unavailable metrics recover with explicit retries')
  production = await preview({ root: resolve('frontend'), preview: { host: '127.0.0.1', port: 5174, strictPort: true } })
  const requests = []
  page.on('request', r => { if (r.url().includes(':8765/')) requests.push('research-request') })
  for (const path of ['/', '/mapa']) {
    await page.goto('http://127.0.0.1:5174' + path, { waitUntil: 'networkidle0' })
    await page.waitForSelector('main .content-wrap')
    assert.equal(new URL(page.url()).pathname, path)
    assert.equal(await page.$('.research-spatial'), null); assert.equal(await page.$('.research-mode'), null)
  }
  assert.deepEqual(requests, [])
  checkpoint('Production preview: original dashboard/map, no A/B control or experimental requests')
  assert.deepEqual(report.pageErrors, [])
  await writeFile(resolve(output, 'result.json'), JSON.stringify(report, null, 2))
} finally {
  await browser.close()
  if (production) await new Promise(resolve => production.httpServer.close(resolve))
}
