// Real read-only walkthrough only with --real; default transport is explicitly fictional.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { preview } from 'vite'
import { fixtureResponse } from '../security/backtest.fixture.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const real = process.argv.includes('--real')
const output = resolve('data/interim/official/historical-backtest-stage3-20261102-v1/browser', real ? 'real' : 'fictional')
await mkdir(output, { recursive: true })
const browser = await puppeteer.launch({ headless: true })
let production
const errors = [], external = [], requests = []
try {
  const page = await browser.newPage()
  page.setDefaultTimeout(20000)
  page.on('pageerror', error => errors.push(error.message))
  let fail = false, delay = false
  await page.setRequestInterception(true)
  page.on('request', async request => {
    const url = new URL(request.url()); if (!['http:', 'https:'].includes(url.protocol)) return request.continue()
    if (url.hostname !== '127.0.0.1' || !['5173', '5174', '8765'].includes(url.port)) { external.push(url.origin); return request.abort() }
    if (url.pathname.startsWith('/api/v1/research/backtest')) {
      if (request.method() === 'OPTIONS') return request.respond({ status: 200, headers: { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173', 'Access-Control-Allow-Methods': 'GET', 'Access-Control-Allow-Headers': 'X-Sigard-Research' } })
      requests.push({ method: request.method(), path: url.pathname })
      assert.equal(request.method(), 'GET')
      assert.equal(request.headers()['x-sigard-research'], 'local-read')
      if (fail && url.pathname.endsWith('/comparison')) return request.respond({ status: 503, headers: { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173' }, body: '{}' })
      if (!real) {
        if (delay && url.pathname.endsWith('/comparison')) await new Promise(r => setTimeout(r, 350))
        return request.respond({ status: 200, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173', 'Cache-Control': 'no-store, private' }, body: JSON.stringify(fixtureResponse(url.href)) })
      }
    }
    return request.continue()
  })
  await page.setViewport({ width: 1440, height: 1050 })
  await page.goto('http://127.0.0.1:5173/mapa', { waitUntil: 'networkidle0' })
  console.log('backtest-browser: application loaded')
  await page.evaluate(() => [...document.querySelectorAll('.research-mode button')].find(b => b.textContent === 'Backtesting histórico').click())
  const ready = () => page.waitForFunction(() => document.querySelector('.bt-territory-table tbody tr') && ![...document.querySelectorAll('.historical-backtest [role="alert"]')].length, { timeout: 30000 })
  await ready()
  console.log('backtest-browser: first week loaded')
  assert.equal(await page.$$eval('.bt-map .leaflet-overlay-pane svg', e => e.length), 2)
  assert.equal(await page.$$eval('.bt-territory-table tbody tr', e => e.length), 263)
  await page.select('#bt-year', '2020'); await ready()
  assert.equal(await page.$$eval('#bt-week option', options => options.length), 53)
  await page.select('#bt-week', '2020-12-27'); await ready()
  await page.waitForFunction(() => document.querySelector('.bt-period').textContent.includes('SE 53/2020'))
  assert.ok(await page.$('.bt-unavailable'))
  await page.select('#bt-year', '2021'); await ready()
  await page.waitForFunction(() => document.querySelector('.bt-period').textContent.includes('2020-12-27 a 2021-01-02'))
  await page.select('#bt-year', '2022'); await ready()
  await page.select('#bt-year', '2024'); await ready()
  await page.select('#bt-week', '2024-03-17'); await ready()
  console.log('backtest-browser: historical controls passed')
  await page.waitForFunction(() => document.querySelector('.bt-period').textContent.includes('SE 12/2024'))
  assert.equal(await page.$('.bt-unavailable'), null)
  const firstRadio = await page.$eval('#bt-radio option:nth-child(2)', e => e.value)
  await page.select('#bt-radio', firstRadio)
  assert.equal(await page.$$eval('.bt-territory-table tbody tr', e => e.length), 1)
  await page.waitForFunction(() => document.querySelector('.bt-history p').textContent.includes(document.querySelector('#bt-radio').value))
  await page.select('#bt-radio', '')
  const screenshot = async name => {
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: resolve(output, name), fullPage: true })
  }
  await page.waitForSelector('.bt-chart svg')
  await screenshot('desktop-presence.private.png')
  await page.select('#bt-view', 'quantity')
  assert.match(await page.$eval('.bt-territory-table', e => e.textContent), /Error absoluto/)
  await screenshot('desktop-quantity.private.png')
  // Same camera and zoom after one map is moved.
  await page.click('.bt-dual-maps figure:first-child .leaflet-control-zoom-in')
  await page.waitForFunction(() => {
    const panes = [...document.querySelectorAll('.bt-map')]
    return panes.length === 2 && panes[0].dataset.btCamera === panes[1].dataset.btCamera
  })
  await page.setViewport({ width: 390, height: 844 })
  await page.waitForFunction(() => {
    const maps = [...document.querySelectorAll('.bt-map')]
    return maps.length === 2 && maps[0].dataset.btCamera === maps[1].dataset.btCamera
  })
  await screenshot('mobile-quantity.private.png')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), false)
  await page.select('#bt-view', 'presence'); await screenshot('mobile-presence.private.png')
  await page.select('#bt-week', '2024-12-22'); await ready()
  assert.equal(await page.$('.bt-unavailable'), null)
  await page.select('#bt-year', '2025'); await ready()
  assert.ok(await page.$('.bt-unavailable'))
  assert.match(await page.$eval('.bt-territory-table tbody', e => e.textContent), /No disponible/)
  if (!real) {
    fail = true; await page.select('#bt-year', '2023')
    await page.waitForSelector('.historical-backtest [role="alert"]')
    assert.equal(await page.$('.bt-territory-table'), null)
    fail = false
    await page.evaluate(() => [...document.querySelectorAll('.historical-backtest button')].find(b => b.textContent === 'Reintentar consulta').click())
    await ready()
    delay = true; await page.select('#bt-year', '2022')
    assert.equal(await page.$('.bt-territory-table'), null, 'no stale maps after changing target')
    await page.select('#bt-year', '2024'); await ready()
    assert.match(await page.$eval('.bt-period', e => e.textContent), /SE 1\/2024/)
    delay = false
  }
  assert.equal(errors.length, 0, JSON.stringify(errors))
  // Production hides all local research controls and issues no private API reads.
  production = await preview({ root: resolve('frontend'), preview: { host: '127.0.0.1', port: 5174, strictPort: true } })
  const previous = requests.length
  await page.goto('http://127.0.0.1:5174/mapa', { waitUntil: 'networkidle0' })
  assert.equal(await page.$('.historical-backtest'), null)
  assert.equal(await page.$('.research-mode'), null)
  assert.equal(requests.length, previous)
  const receipt = { status: 'passed', source: real ? 'private_real_aggregate_read_only' : 'generated_fictional_transport_only',
    requests: requests.length, browser_errors: errors, external_requests_blocked: [...new Set(external)],
    no_training: true, no_private_api_in_production: true, fixtures_in_epidemiological_metrics: false }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify(receipt))
} finally { await browser.close(); if (production) await new Promise(r => production.httpServer.close(r)) }
