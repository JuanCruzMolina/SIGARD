// Reproducible performance measurement for the acceptance criterion (c): p95 < 5 s.
// Owns its environments (ports 5173, 8765, 8767 and the fixture API must be free):
//   phase 1: `dev` (Vite + local predictive API, protected mode) + fixture public API
//            (fictional activity package, versioned prevention guidance);
//   phase 2: `dev:alerts` in session mode (disposable SQLite, generated admin) over the
//            local predictive API (protected values).
// Each operation: 30 repetitions with 1 simulated user, and 30 rounds with 5 concurrent users
// (separate browser contexts, 150 samples). Nearest-rank p95. Only timings are recorded.
// Usage (repository root): node frontend/scripts/performance.browser.mjs [--reps 30]
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { cpus, totalmem, release, platform } from 'node:os'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { proxyRequest } from './browser-proxy.mjs'
import { developmentRuntime, portAvailable, startDevelopment } from './dev.mjs'
import { alertsRuntime } from './dev-alerts.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const output = resolve(root, 'data/interim/official/performance-v1')
const origin = 'http://127.0.0.1:5173'
const reps = Number(process.argv[process.argv.indexOf('--reps') + 1]) || 30
// --only a,b re-measures selected operations (results file per run label).
const only = process.argv.includes('--only') ? new Set(process.argv[process.argv.indexOf('--only') + 1].split(',')) : null
const selected = name => !only || only.has(name)
const USERS = [1, 5]
const THRESHOLD_MS = 5000
const delay = ms => new Promise(r => setTimeout(r, ms))
const results = []

function p95(values) {
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.ceil(0.95 * sorted.length) - 1]
}
function summarize(operation, users, samples, timeouts = 0) {
  const sorted = [...samples].sort((a, b) => a - b)
  const row = { operation, users, n: samples.length, timeouts, p50_ms: sorted[Math.floor(sorted.length / 2)], p95_ms: p95(samples), max_ms: sorted.at(-1) }
  row.pass = row.p95_ms < THRESHOLD_MS
  results.push(row)
  void writeFile(resolve(output, 'results.partial.json'), JSON.stringify({ results, failures }, null, 2)).catch(() => {})
  console.log(`${operation.padEnd(26)} usuarios=${users} n=${row.n} agotados=${timeouts} p50=${row.p50_ms} p95=${row.p95_ms} max=${row.max_ms} ${row.pass ? 'OK' : 'SUPERA 5 s'}`)
}

function startFixture() {
  const child = spawn(resolve(root, 'backend/.venv/Scripts/python.exe'), ['-B', 'backend/tests/browser_activity_fixture.py', '--fixture', '--prevention'],
    { cwd: root, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true })
  const closed = new Promise(r => child.once('exit', r))
  const ready = new Promise((ok, fail) => {
    let out = ''
    child.stdout.on('data', d => { out += d; if (out.includes('\n')) ok(JSON.parse(out.split('\n')[0])) })
    child.once('exit', () => fail(new Error('La API ficticia terminó')))
  })
  return { ready, async stop() { child.stdin.end('stop\n'); if (!await Promise.race([closed.then(() => true), delay(5000).then(() => false)])) child.kill() } }
}

async function newPage(browser, { fixturePort } = {}) {
  const context = await browser.createBrowserContext()
  const page = await context.newPage()
  page.setDefaultTimeout(SAMPLE_TIMEOUT_MS)
  await page.setViewport({ width: 1440, height: 1000 })
  if (fixturePort) {
    await page.setRequestInterception(true)
    page.on('request', request => {
      const url = new URL(request.url())
      if (url.port === '8000' && url.pathname.startsWith('/api/v1/')) return proxyRequest(request, `http://127.0.0.1:${fixturePort}${url.pathname}${url.search}`)
      // Street tiles and web fonts are excluded so the network outside this machine does not count.
      if (!['127.0.0.1', 'localhost'].includes(url.hostname) && url.protocol.startsWith('http')) return request.abort()
      return request.continue()
    })
  }
  return { page, close: () => context.close() }
}

// Runs `measure(user)` with 1 user (reps samples) and with 5 concurrent users (reps rounds).
async function measureOperation(name, setup, measure) {
  if (!selected(name)) return
  for (const users of USERS) {
    const sessions = []
    for (let i = 0; i < users; i++) sessions.push(await setup(i))
    const samples = []
    for (let round = 0; round < reps; round++) {
      const times = await Promise.all(sessions.map(session => measure(session, round)))
      samples.push(...times)
    }
    for (const session of sessions) await session.close?.()
    summarize(name, users, samples, failures.filter(f => f.operation === name && !f.counted).map(f => { f.counted = true; return f }).length)
  }
}

const SAMPLE_TIMEOUT_MS = 30000
const failures = []
const pageState = page => page.evaluate(() => ({ path: location.pathname, state: document.querySelector('.pv')?.dataset.state ?? null,
  updating: Boolean(document.querySelector('.pv-updating')), polygons: document.querySelectorAll('path.leaflet-interactive').length,
  messages: [...document.querySelectorAll('[role="alert"],[role="status"]')].map(e => e.textContent.trim()).filter(Boolean).slice(0, 5) })).catch(() => null)
// A sample that does not finish within SAMPLE_TIMEOUT_MS is kept as a failure, never dropped.
async function timed(run, page, operation) {
  const start = performance.now()
  try { await run() } catch (error) {
    failures.push({ operation, error: error.name, elapsed_ms: Math.round(performance.now() - start), state: page ? await pageState(page) : null })
    return Math.max(SAMPLE_TIMEOUT_MS, Math.round(performance.now() - start))
  }
  return Math.round(performance.now() - start)
}

let browser, devSession, fixture, alertsSession
const startedAt = new Date().toISOString()
try {
  for (const port of [5173, 8765, 8767]) assert.ok(await portAvailable(port), `El puerto ${port} debe estar libre`)
  await mkdir(output, { recursive: true })
  browser = await puppeteer.launch({ headless: true })
  const browserVersion = await browser.version()

  // Phase 1: dev + fixture public API.
  developmentRuntime.log = () => {}
  devSession = await startDevelopment(developmentRuntime)
  fixture = startFixture()
  const { port: fixturePort } = await fixture.ready
  // Cold operations open a new browser context per sample; no state is shared between samples.
  const fresh = () => async () => ({})

  await measureOperation('actividad_carga_fixture', fresh(), async () => {
    const { page, close } = await newPage(browser, { fixturePort })
    const ms = await timed(async () => {
      await page.goto(`${origin}/actividad`, { waitUntil: 'domcontentloaded' })
      await page.waitForFunction(() => document.querySelectorAll('.pa-map path.leaflet-interactive').length === 25 && document.querySelector('.pa-series .pa-bar'))
    }, page, 'actividad_carga_fixture')
    await close(); return ms
  })

  await measureOperation('prevencion_carga', fresh(), async () => {
    const { page, close } = await newPage(browser, { fixturePort })
    const ms = await timed(async () => {
      await page.goto(`${origin}/prevencion`, { waitUntil: 'domcontentloaded' })
      await page.waitForFunction(() => document.querySelectorAll('.facility-marker').length === 27 && (document.querySelector('.prevention-content')?.textContent.length || 0) > 500)
    }, page, 'prevencion_carga')
    await close(); return ms
  })

  const visorReady = (page, timeout = SAMPLE_TIMEOUT_MS) => page.waitForFunction(() => document.querySelector('.pv')?.dataset.state === 'ready' && !document.querySelector('.pv-updating')
    && document.querySelectorAll('.pv-map path.leaflet-interactive').length >= 263, { timeout })
  await measureOperation('visor_carga', fresh(), async () => {
    const { page, close } = await newPage(browser, { fixturePort })
    const ms = await timed(async () => { await page.goto(`${origin}/mapa`, { waitUntil: 'domcontentloaded' }); await visorReady(page) }, page, 'visor_carga')
    await close(); return ms
  })

  const loadedVisor = async () => {
    const session = await newPage(browser, { fixturePort })
    await session.page.goto(`${origin}/mapa`, { waitUntil: 'domcontentloaded' }); await visorReady(session.page, 120000)
    // The viewer keeps loading yearly histories in the background; an "already loaded" viewer
    // is one whose background requests finished, so they do not queue behind the next setup.
    await session.page.waitForNetworkIdle({ idleTime: 1500, timeout: 300000 })
    return session
  }
  await measureOperation('visor_cambio_semana', loadedVisor, async ({ page }) => {
    const before = await page.$eval('.pv', e => e.dataset.week)
    return timed(async () => {
      await page.click('button[aria-label="Semana anterior"]')
      await page.waitForFunction(previous => { const v = document.querySelector('.pv'); return v.dataset.week !== previous && v.dataset.state === 'ready' && !document.querySelector('.pv-updating') }, {}, before)
    }, page, 'visor_cambio_semana')
  })

  let radios
  await measureOperation('visor_consulta_radio', loadedVisor, async ({ page }, round) => {
    radios ??= await page.$$eval('#pv-radio option', o => o.map(e => e.value).filter(Boolean))
    const id = radios[(round * 7) % radios.length]
    return timed(async () => {
      await page.select('#pv-radio', id)
      await page.waitForFunction(id => document.querySelector('.pv-panel')?.textContent.includes(id) && !document.querySelector('.pv-updating'), {}, id)
    }, page, 'visor_consulta_radio')
  })
  await fixture.stop(); fixture = undefined
  await devSession.stop(); await devSession.closed; devSession = undefined

  // Phase 2: dev:alerts (session mode, protected values from the local predictive API).
  const runtime = alertsRuntime({ mode: 'session', source: 'local-research' })
  runtime.announce = () => {}; runtime.log = () => {}
  alertsSession = await startDevelopment(runtime)
  const { email, password } = runtime.service.credentials
  // The login limiter allows 5 attempts per 15 min and address: log in once and give every
  // simulated user its own browser context with that session token.
  let token
  const loggedIn = async () => {
    const session = await newPage(browser)
    const { page } = session
    if (token) {
      await page.evaluateOnNewDocument(value => sessionStorage.setItem('sigard_admin_token', value), token)
      return session
    }
    for (let attempt = 0; attempt < 3; attempt++) {
      await page.goto(`${origin}/admin/reportes`, { waitUntil: 'domcontentloaded', timeout: 120000 })
      await page.waitForSelector('.admin-login input[type="email"]', { timeout: 120000 })
      await page.type('.admin-login input[type="email"]', email); await page.type('.admin-login input[type="password"]', password)
      await page.evaluate(() => [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Ingresar').click())
      const ok = await page.waitForSelector('.admin-header', { timeout: 10000 }).then(() => true, () => false)
      if (ok) { token = await page.evaluate(() => sessionStorage.getItem('sigard_admin_token')); return session }
      await delay(61000) // login rate limit window
    }
    throw new Error('No se pudo iniciar sesión en la API de alertas')
  }
  await measureOperation('panel_alertas', loggedIn, async ({ page }) => {
    await page.goto(`${origin}/admin/reportes`, { waitUntil: 'domcontentloaded', timeout: 120000 })
    await page.waitForSelector('.admin-header', { timeout: 120000 })
    return timed(async () => {
      await page.evaluate(() => [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Alertas internas').click())
      await page.waitForFunction(() => document.querySelector('.alerts-banner') && document.querySelectorAll('.alerts-evaluate option').length > 0)
    }, page, 'panel_alertas')
  })

  const environment = {
    started_at: startedAt, finished_at: new Date().toISOString(), cpu: cpus()[0]?.model, logical_cores: cpus().length,
    ram_gb: Math.round(totalmem() / 2 ** 30), os: `${platform()} ${release()}`, node: process.version, browser: browserVersion,
    mode: 'Vite dev server (sin bundle de producción), APIs locales uvicorn, Chromium headless en el mismo equipo; teselas y fuentes externas excluidas',
    volume: '263 radios oficiales; visor con 208 semanas evaluables 2021–2024; actividad con fixture de 24 celdas + 1 fuera del área, 45 bloques',
    repetitions: reps, concurrency: USERS, percentile: 'p95 por rango más cercano', threshold_ms: THRESHOLD_MS,
  }
  await writeFile(resolve(output, only ? `results-${[...only].join('+')}.json` : 'results.json'), JSON.stringify({ environment, results, failures }, null, 2))
  console.log(JSON.stringify({ environment, all_pass: results.every(r => r.pass) }))
} finally {
  await browser?.close()
  await fixture?.stop()
  if (devSession) { await devSession.stop(); await devSession.closed }
  if (alertsSession) { await alertsSession.stop(); await alertsSession.closed }
}
