// Browser check of the public activity view with the generated fictional package only.
// Run Vite first with the normal dev command. This script owns its disposable fixture APIs.
// Screenshots go to a private, Git-ignored folder; no real package is read.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ADMIN_API_PORTS, proxyRequest } from './browser-proxy.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'
import { auditAccessibility, tabReaches } from './browser-a11y.mjs'
import { blockLabel, blockRange, periodBanner, periodText } from '../src/services/publicActivity.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
// Private screenshots: a new folder per run label (SIGARD_SHOTS_LABEL, timestamp by default); never overwritten.
const outputBase = resolve(root, 'data/interim/official/public-activity-review-v1')
const label = runLabel()
let output
const origin = 'http://127.0.0.1:5173'
const delay = ms => new Promise(r => setTimeout(r, ms))
const report = { checks: [], timings: {}, pageErrors: [], external: [], accessibility: [], fixture: 'generated fictional package' }

function startFixture(enabled) {
  const child = spawn(resolve(root, 'backend/.venv/Scripts/python.exe'), ['-B', 'backend/tests/browser_activity_fixture.py', ...(enabled ? ['--fixture'] : [])],
    { cwd: root, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true })
  let errors = ''
  child.stderr.on('data', d => { errors += d })
  const closed = new Promise(r => child.once('exit', r))
  const ready = new Promise((resolveReady, reject) => {
    let out = ''
    const timer = setTimeout(() => reject(new Error('No inició la API ficticia')), 20000)
    child.stdout.on('data', d => { out += d; if (out.includes('\n')) { clearTimeout(timer); resolveReady(JSON.parse(out.split('\n')[0])) } })
    child.once('exit', () => { clearTimeout(timer); reject(new Error(`La API ficticia terminó: ${errors}`)) })
  })
  return { ready, errors: () => errors, async stop() { child.stdin.end('stop\n'); if (!await Promise.race([closed.then(() => true), delay(5000).then(() => false)])) child.kill() } }
}

// `failActivity`: answer the first N activity requests with 503 (transient-failure retry check).
async function openPage(browser, port, { failActivity = 0 } = {}) {
  const page = await browser.newPage()
  page.setDefaultTimeout(15000)
  page.on('pageerror', e => report.pageErrors.push(e.message))
  await page.setRequestInterception(true)
  page.on('request', request => {
    const url = new URL(request.url())
    if (ADMIN_API_PORTS.includes(url.port) && url.pathname === '/api/v1/public/activity' && failActivity > 0 && request.method() === 'GET') {
      failActivity -= 1; report.injected503 = (report.injected503 || 0) + 1
      return request.respond({ status: 503, headers: { 'access-control-allow-origin': origin }, body: '' })
    }
    if (ADMIN_API_PORTS.includes(url.port) && url.pathname.startsWith('/api/v1/')) return proxyRequest(request, `http://127.0.0.1:${port}${url.pathname}${url.search}`)
    if (!['127.0.0.1', 'localhost'].includes(url.hostname) && url.protocol.startsWith('http')) { report.external.push(url.origin); return request.abort() }
    return request.continue()
  })
  return page
}

async function accessibility(page, context) {
  const cdp = await page.target().createCDPSession()
  const tree = await cdp.send('Accessibility.getFullAXTree')
  await cdp.detach()
  const unnamed = tree.nodes.filter(n => !n.ignored && ['button', 'combobox', 'checkbox', 'link'].includes(n.role?.value) && !n.name?.value?.trim()).map(n => n.role.value)
  const contrast = await page.evaluate(() => {
    const rgb = s => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number)
    const lum = c => c.map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0)
    const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05) }
    return ['.pa-banner strong', '.pa-legend li', '.pa-facts dt', '.pa-series-note', '.pa-provenance p', '.pa-explain p', '.pa-fixture'].map(selector => {
      const e = document.querySelector(selector); if (!e) return { selector, missing: true }
      let bg = null; for (let p = e; p && !bg; p = p.parentElement) { const c = getComputedStyle(p).backgroundColor; if (!c.includes('rgba(0, 0, 0, 0)') && c !== 'transparent') bg = rgb(c) }
      return { selector, ratio: Number(ratio(rgb(getComputedStyle(e).color), bg || [255, 255, 255]).toFixed(2)) }
    })
  })
  report.accessibility.push({ context, unnamed, contrast })
  assert.deepEqual(unnamed, [], `controles sin nombre en ${context}`)
  for (const item of contrast) { assert.ok(!item.missing, `${item.selector} ausente`); assert.ok(item.ratio >= 4.5, `contraste ${item.selector} ${item.ratio}`) }
}

const check = async (name, run) => { await run(); report.checks.push(name) }
let browser
const enabled = startFixture(true)
let disabled
try {
  const { port } = await enabled.ready
  const fixture = await (await fetch(`http://127.0.0.1:${port}/api/v1/public/activity`)).json()
  assert.equal(fixture.source.fictional, true)
  browser = await puppeteer.launch({ headless: true })
  let page = await openPage(browser, port)
  await page.setViewport({ width: 1440, height: 1000 })

  await check('vista habilitada con fixture: carga en menos de 5 s', async () => {
    const start = Date.now()
    await page.goto(`${origin}/actividad`, { waitUntil: 'domcontentloaded' })
    await page.waitForFunction(n => document.querySelectorAll('.pa-map path.leaflet-interactive').length === n, {}, fixture.geometry.features.length)
    await page.waitForSelector('.pa-series svg .pa-bar')
    report.timings.cold_start_ms = Date.now() - start
    assert.ok(report.timings.cold_start_ms < 5000, `carga ${report.timings.cold_start_ms} ms`)
  })

  await check('reintento: una falla transitoria (503) y la vista igual muestra los datos', async () => {
    const retry = await openPage(browser, port, { failActivity: 1 })
    await retry.setViewport({ width: 1440, height: 1000 })
    await retry.goto(`${origin}/actividad`, { waitUntil: 'domcontentloaded' })
    await retry.waitForFunction(n => document.querySelectorAll('.pa-map path.leaflet-interactive').length === n, {}, fixture.geometry.features.length)
    assert.equal(await retry.$('.pa-disabled'), null)
    await retry.close()
  })

  await check('dos fallas seguidas: la vista falla cerrada (no habilitada)', async () => {
    const failing = await openPage(browser, port, { failActivity: 2 })
    await failing.setViewport({ width: 1440, height: 1000 })
    await failing.goto(`${origin}/actividad`, { waitUntil: 'domcontentloaded' })
    await failing.waitForSelector('.pa-disabled')
    assert.equal(await failing.$('.pa-map path.leaflet-interactive'), null)
    await failing.close()
  })

  const expectBannerAndPeriod = async block => {
    assert.equal(await page.$eval('[data-testid="historical-banner"]', e => e.textContent.trim()), periodBanner(fixture))
    assert.ok(await page.$eval('[data-testid="historical-banner"]', e => { const r = e.getBoundingClientRect(); return r.height > 0 && getComputedStyle(e).visibility !== 'hidden' }))
    assert.equal(await page.$eval('[data-testid="period"]', e => e.textContent), periodText(fixture))
    assert.equal(await page.$eval('[data-testid="block-range"]', e => e.textContent), `${blockLabel(block)} · ${blockRange(block)}`)
  }

  await check('banner histórico, período, rango del bloque y fecha de generación separada', async () => {
    assert.match(periodBanner(fixture), /^Datos históricos: período SE 1–4\/2020 a SE 21–24\/2024\. No reflejan la situación actual\.$/)
    await expectBannerAndPeriod(fixture.blocks.at(-1))
    const provenance = await page.$eval('.pa-provenance', e => e.textContent)
    assert.match(provenance, /Paquete generado el 16\/11\/2026/)
    assert.match(provenance, /no indica que los datos sean actuales/)
    assert.match(await page.$eval('.pa-fixture', e => e.textContent), /Datos ficticios de prueba/)
    assert.equal(await page.$eval('.main-nav a[href="/actividad"]', e => e.textContent), 'Actividad registrada')
  })

  await check('banner y período presentes en todos los bloques (selector por teclado)', async () => {
    await page.focus('#pa-block')
    await page.keyboard.press('Home')
    for (const block of fixture.blocks) {
      await page.waitForFunction(id => document.querySelector('#pa-map-title')?.textContent.includes(id), {}, blockLabel(block))
      await expectBannerAndPeriod(block)
      await page.keyboard.press('ArrowDown')
    }
    await page.click('button[aria-label="Bloque anterior"]')
    await expectBannerAndPeriod(fixture.blocks.at(-2))
  })

  await check('niveles con trama para protegido, leyenda y textos de privacidad', async () => {
    const block = fixture.blocks.at(-2)
    const fills = await page.$$eval('.pa-map path.leaflet-interactive', n => n.map(p => p.getAttribute('fill')))
    assert.ok(fills.includes('url(#pa-hatch-protected)'))
    assert.equal(fills.filter(f => f === 'url(#pa-hatch-protected)').length, Object.values(block.radios).filter(l => l === 'protegido').length)
    const legend = await page.$eval('.pa-legend', e => e.textContent)
    for (const text of ['Menos de 5 registros (protegido)', 'Bajo', 'Medio', 'Alto', '20 o más registros', 'Fuera del área analizada']) assert.ok(legend.includes(text), text)
    const body = await page.$eval('.pa-view', e => e.textContent)
    assert.ok(body.includes('Datos agregados por zona; no muestran domicilios.'))
    assert.ok(body.includes('2022 no se incluye: ese año los registros tienen una clasificación distinta'))
    assert.ok(!/\b2022-B\d\d\b/.test(await page.$eval('#pa-block', e => e.innerHTML)))
  })

  await check('teclado: bloque, radio y tablas alcanzables con Tab', async () => {
    for (const selector of ['#pa-block', '#pa-radio', '.pa-series summary']) assert.ok(await tabReaches(page, selector), `${selector} alcanzable con Tab`)
  })

  await check('selector de radio, serie semanal y tablas equivalentes', async () => {
    await page.select('#pa-radio', 'FICT-001')
    await page.waitForFunction(() => document.querySelector('.pa-radio p')?.textContent.includes('Radio FICT-001'))
    const block = fixture.blocks.at(-2)
    const year = fixture.blocks.filter(b => b.year === block.year).flatMap(b => b.city_weeks)
    assert.equal(await page.$$eval('.pa-series .pa-hit', n => n.length), year.length)
    await page.click('.pa-series summary')
    assert.equal(await page.$$eval('.pa-series tbody tr', n => n.length), year.length)
    const cells = await page.$$eval('.pa-series tbody td:last-child', n => n.map(e => e.textContent))
    assert.ok(cells.every(c => c === '<5' || c === 'Oculto' || Number(c) >= 5))
    await page.hover('.pa-series .pa-hit')
    await page.waitForSelector('.pa-tooltip')
  })

  await check('calles atenuadas sin conexión y sin solicitudes externas permitidas', async () => {
    await page.waitForFunction(() => document.querySelector('.pa-basemap-offline')?.textContent.includes('sin conexión'))
    assert.ok(report.external.every(o => /tile.openstreetmap.org/.test(o)), [...new Set(report.external)].join(', '))
  })

  output = await newRunDirectory(outputBase, label)
  await check('escritorio y móvil sin desborde, banner fijo al desplazarse, accesibilidad', async () => {
    for (const width of [1440, 390]) {
      await page.setViewport({ width, height: 1000 })
      await delay(150)
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `desborde a ${width}px`)
      // .app-shell clips horizontal overflow, so measure element edges instead of scrollWidth.
      const clipped = await page.evaluate(() => [...document.querySelectorAll('.pa-view *, .page-intro *')]
        .filter(e => !e.closest('.leaflet-container, .pa-table-scroll, svg, .pa-hatches, .pa-sr') && e.getClientRects().length)
        .filter(e => e.getBoundingClientRect().right > innerWidth + 1).map(e => e.className || e.tagName).slice(0, 5))
      assert.deepEqual(clipped, [], `elementos cortados a ${width}px`)
      await accessibility(page, `activity-${width}`)
      const full = await auditAccessibility(page, 'main')
      assert.deepEqual(full.unnamed, [], `actividad: controles sin nombre (${width}px)`)
      assert.deepEqual(full.lowContrast, [], `actividad: contraste insuficiente (${width}px)`)
      await page.screenshot({ path: resolve(output, `activity-fixture-${width}.png`), fullPage: true })
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
      await delay(100)
      const visible = await page.$eval('[data-testid="historical-banner"]', e => { const r = e.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight })
      if (width === 1440 || width === 390) assert.ok(visible, `banner no visible al desplazarse (${width}px)`)
      await page.screenshot({ path: resolve(output, `activity-fixture-${width}-scrolled.png`) })
      await page.evaluate(() => window.scrollTo(0, 0))
    }
  })
  await page.close()
  await enabled.stop()

  disabled = startFixture(false)
  const off = await disabled.ready
  assert.equal(off.enabled, false)
  page = await openPage(browser, off.port)
  await page.setViewport({ width: 1440, height: 1000 })
  await check('bandera desactivada por defecto: sin enlace, vista no habilitada, mapa actual intacto', async () => {
    assert.equal((await fetch(`http://127.0.0.1:${off.port}/api/v1/public/activity`)).status, 404)
    await page.goto(`${origin}/actividad`, { waitUntil: 'networkidle0' })
    await page.waitForSelector('.pa-disabled')
    assert.equal(await page.$('.pa-banner'), null)
    assert.equal(await page.$('.main-nav a[href="/actividad"]'), null)
    await page.screenshot({ path: resolve(output, 'activity-disabled-1440.png') })
    await page.click('.main-nav a[href="/mapa"]')
    // Wait for the route change: the previous heading is still in the DOM right after the click.
    await page.waitForFunction(() => location.pathname === '/mapa' && document.querySelector('.page-intro h1')?.textContent !== 'Actividad registrada')
  })
  assert.deepEqual(report.pageErrors, [])
  assert.equal(enabled.errors(), '')
  assert.equal(disabled.errors(), '')
  await writeFile(resolve(output, 'browser-result.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify({ ...report, accessibility: report.accessibility.map(a => ({ context: a.context, unnamed: a.unnamed.length, minContrast: Math.min(...a.contrast.map(c => c.ratio)) })), external: [...new Set(report.external)] }))
} finally {
  await browser?.close()
  await enabled.stop()
  await disabled?.stop()
}
