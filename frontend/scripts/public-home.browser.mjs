// Browser check of the public home page (Situación actual) at 390 px and desktop.
// Owns its Vite (5175) and two disposable loopback APIs: the generated fictional activity package
// (plus the versioned public prevention guidance) and a disabled one (404) for the empty state.
// Screenshots go to frontend/.tmp/public-home-review/<label>/ (ignored by Git); data/ is never written.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ADMIN_API_PORTS, proxyRequest } from './browser-proxy.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'
import { auditAccessibility, tabReaches } from './browser-a11y.mjs'
import { spawnOwned } from './dev.mjs'
import { EMPTY, FICTIONAL_NOTICE } from '../src/services/publicHome.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const outputBase = resolve(root, 'frontend/.tmp/public-home-review')
const origin = 'http://127.0.0.1:5175'
const delay = ms => new Promise(r => setTimeout(r, ms))
const report = { checks: [], pageErrors: [], external: [], accessibility: [], fixture: 'generated fictional activity package + versioned public prevention guidance' }
const check = async (name, run) => { await run(); report.checks.push(name) }

function startApi(fixture) {
  const args = ['-B', 'backend/tests/browser_activity_fixture.py', '--prevention', ...(fixture ? ['--fixture'] : [])]
  const child = spawn(resolve(root, 'backend/.venv/Scripts/python.exe'), args,
    { cwd: root, env: { ...process.env, SIGARD_BROWSER_FRONTEND_URL: origin }, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true })
  let errors = ''
  child.stderr.on('data', d => { errors += d })
  const closed = new Promise(r => child.once('exit', r))
  const ready = new Promise((resolveReady, reject) => {
    let out = ''
    const timer = setTimeout(() => reject(new Error('No inició la API ficticia')), 30000)
    child.stdout.on('data', d => { out += d; if (out.includes('\n')) { clearTimeout(timer); resolveReady(JSON.parse(out.split('\n')[0])) } })
    child.once('exit', () => { clearTimeout(timer); reject(new Error(`La API ficticia terminó: ${errors}`)) })
  })
  return { ready, errors: () => errors, async stop() { child.stdin.end('stop\n'); if (!await Promise.race([closed.then(() => true), delay(5000).then(() => false)])) child.kill() } }
}

async function openPage(browser, port) {
  const page = await browser.newPage()
  page.setDefaultTimeout(15000)
  page.on('pageerror', e => report.pageErrors.push(e.message))
  await page.setRequestInterception(true)
  page.on('request', request => {
    const url = new URL(request.url())
    if (ADMIN_API_PORTS.includes(url.port) && url.pathname.startsWith('/api/v1/')) return proxyRequest(request, `http://127.0.0.1:${port}${url.pathname}${url.search}`)
    if (!['127.0.0.1', 'localhost'].includes(url.hostname) && url.protocol.startsWith('http')) { report.external.push(url.origin); return request.abort() }
    return request.continue()
  })
  return page
}

// Layout and readability at one width: no horizontal scroll, nothing cut, body text >= 16 px, AA contrast.
async function layout(page, context) {
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `desborde horizontal (${context})`)
  const clipped = await page.evaluate(() => [...document.querySelectorAll('.public-home *')]
    .filter(e => !e.closest('svg') && e.getClientRects().length && e.getBoundingClientRect().right > innerWidth + 1).map(e => e.className || e.tagName).slice(0, 5))
  assert.deepEqual(clipped, [], `elementos cortados (${context})`)
  const small = await page.evaluate(() => [...document.querySelectorAll('.public-home p, .public-home li, .public-home a, .public-home small, .public-home span, .public-home button')]
    .filter(e => !e.closest('svg') && e.textContent.trim() && e.getClientRects().length && parseFloat(getComputedStyle(e).fontSize) < 16)
    .map(e => `${e.tagName}.${e.className}: ${getComputedStyle(e).fontSize}`).slice(0, 5))
  assert.deepEqual(small, [], `texto menor a 16 px (${context})`)
  const audit = await auditAccessibility(page, '.public-home')
  report.accessibility.push({ context, unnamed: audit.unnamed.length, lowContrast: audit.lowContrast })
  assert.deepEqual(audit.unnamed, [], `controles sin nombre (${context})`)
  assert.deepEqual(audit.lowContrast, [], `contraste insuficiente (${context})`)
}

const inViewport = (page, selector) => page.$eval(selector, e => { const r = e.getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0 })

let browser, vite, fixtureApi, disabledApi, output
try {
  vite = spawnOwned(process.execPath, ['frontend/node_modules/vite/bin/vite.js', 'frontend', '--host', '127.0.0.1', '--port', '5175', '--strictPort'],
    { cwd: root, env: { ...process.env, VITE_API_URL: 'http://localhost:8000' }, silent: true })
  for (let attempt = 0; attempt < 100; attempt++) {
    try { if ((await fetch(origin)).ok) break } catch { /* owned Vite starting */ }
    await delay(100)
  }
  fixtureApi = startApi(true)
  const { port } = await fixtureApi.ready
  const fixture = await (await fetch(`http://127.0.0.1:${port}/api/v1/public/activity`)).json()
  assert.equal(fixture.source.fictional, true)
  output = await newRunDirectory(outputBase, runLabel())
  browser = await puppeteer.launch({ headless: true })
  let page = await openPage(browser, port)

  for (const width of [390, 1440]) {
    await check(`paquete ficticio a ${width} px: aviso visible, fecha del dato, tendencia y calendario`, async () => {
      await page.setViewport({ width, height: 900 })
      await page.goto(`${origin}/`, { waitUntil: 'networkidle0' })
      await page.waitForSelector('[data-testid="trend"]')
      await page.waitForSelector('.home-cards article')
      const notices = await page.$$eval('[data-testid="fictional-notice"]', n => n.map(e => ({ text: e.textContent, visible: e.getBoundingClientRect().height > 0, section: e.closest('section').id })))
      assert.deepEqual(notices.map(n => n.section), ['situacion', 'calendario'])
      assert.ok(notices.every(n => n.visible && n.text.startsWith(`${FICTIONAL_NOTICE}.`)))
      assert.match(await page.$eval('#situacion [data-testid="data-date"]', e => e.textContent), /^Datos hasta el \d+ de [a-z]+ de 2024\. Es una reconstrucción histórica/)
      assert.equal(await page.$$eval('#situacion .home-bars li', n => n.length), 8)
      const calendarText = await page.$eval('#calendario', e => e.textContent)
      assert.doesNotMatch(calendarText, /\bSE\b|[Bb]loque \d/)
      assert.doesNotMatch(await page.$eval('.public-home', e => e.textContent), /predic|simulaci|percentil|ranking|modelo|<5/i)
      assert.equal(await page.$$eval('[data-slug]', n => n.length), 5)
      assert.match(await page.$eval('[data-testid="emergency-call"]', e => e.getAttribute('href')), /^tel:/)
      await layout(page, `ficticio-${width}`)
      await page.screenshot({ path: resolve(output, `portada-ficticia-${width}.png`), fullPage: true })
    })
  }

  await check('calendario: los botones de año cambian el período mostrado, con teclado', async () => {
    const years = await page.$$eval('.home-years button', n => n.map(e => e.textContent))
    assert.deepEqual(years, ['2020', '2021', '2023', '2024'])
    assert.ok(await tabReaches(page, '.home-years button'), 'botón de año alcanzable con Tab')
    await page.click('.home-years button:first-child')
    await page.waitForFunction(() => document.querySelector('#calendario h3')?.textContent.endsWith('2020'))
    assert.equal(await page.$eval('.home-years button:first-child', e => e.getAttribute('aria-pressed')), 'true')
    assert.equal(await page.$$eval('#calendario .home-bars li', n => n.length), 13)
    assert.ok((await page.$$eval('#calendario .home-bars li.protected', n => n.length)) > 0)
    assert.equal(await page.$$eval('.home-bars li.protected .bar-fill', n => n.length), 0)
    assert.doesNotMatch(await page.$eval('[data-testid="peaks"]', e => e.textContent), /de (\d{4}) de \d{4}/)
  })

  await check('los tres accesos llevan a su destino', async () => {
    await page.setViewport({ width: 390, height: 900 })
    for (const [label, path, anchor] of [['Cómo prevenir', '/prevencion', '#prevenir'], ['Reportar un posible criadero', '/prevencion', '#reportar']]) {
      await page.goto(`${origin}/`, { waitUntil: 'networkidle0' })
      const [link] = await page.$$(`xpath/.//nav[@aria-label="Accesos principales"]//a[contains(., "${label}")]`)
      await link.click()
      await page.waitForFunction(p => location.pathname === p, {}, path)
      await page.waitForSelector(anchor)
      await page.waitForFunction(s => { const r = document.querySelector(s).getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0 }, {}, anchor)
      assert.ok(await inViewport(page, anchor), `${anchor} visible`)
    }
    await page.goto(`${origin}/`, { waitUntil: 'networkidle0' })
    await page.click('nav[aria-label="Accesos principales"] a[href="/mapa"]')
    await page.waitForFunction(() => location.pathname === '/mapa' && document.querySelector('.page-intro h1')?.textContent === 'Mapa público agregado')
  })
  await page.close()
  await fixtureApi.stop()

  disabledApi = startApi(false)
  const off = await disabledApi.ready
  assert.equal((await fetch(`http://127.0.0.1:${off.port}/api/v1/public/activity`)).status, 404)
  page = await openPage(browser, off.port)
  for (const width of [390, 1440]) {
    await check(`estado vacío a ${width} px: sin paquete autorizado, sin aviso ficticio ni cifras`, async () => {
      await page.setViewport({ width, height: 900 })
      await page.goto(`${origin}/`, { waitUntil: 'networkidle0' })
      await page.waitForSelector('#situacion .home-empty')
      await page.waitForSelector('.home-cards article')
      assert.equal(await page.$eval('#situacion .home-empty', e => e.textContent), EMPTY.activityDisabled)
      assert.equal(await page.$eval('#calendario .home-empty', e => e.textContent), EMPTY.calendarDisabled)
      assert.equal(await page.$('[data-testid="fictional-notice"]'), null)
      assert.equal(await page.$('.home-bars'), null)
      await layout(page, `vacio-${width}`)
      await page.screenshot({ path: resolve(output, `portada-vacia-${width}.png`), fullPage: true })
    })
  }
  assert.deepEqual(report.pageErrors, [])
  assert.equal(disabledApi.errors(), '')
  await writeFile(resolve(output, 'browser-result.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify({ output, checks: report.checks, pageErrors: report.pageErrors, external: [...new Set(report.external)], accessibility: report.accessibility.map(a => ({ context: a.context, unnamed: a.unnamed, lowContrast: a.lowContrast.length })) }, null, 1))
} finally {
  await browser?.close()
  await fixtureApi?.stop()
  await disabledApi?.stop()
  await vite?.stop()
}
