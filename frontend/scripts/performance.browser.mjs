// Reproducible performance measurement for the acceptance criterion (c): p95 < 5 s.
// Owns its environments (ports 5173, 8767 and the fixture API must be free):
//   phase 1: Vite + fixture public API (fictional activity package, versioned prevention guidance);
//   phase 2: `dev` runtime in session mode (disposable SQLite, generated admin): the local
//            administrative API (8767) with the predictive viewer routes (F2: administrator
//            session required, protected values) and the alerts panel. One login through the
//            API; every simulated user gets its own browser context with that session token.
// Each operation: 30 repetitions with 1 simulated user, and 30 rounds with 5 concurrent users
// (separate browser contexts, 150 samples). Nearest-rank p95. Only timings are recorded.
// --target production measures the optimized bundle instead of the Vite dev server: `vite build`
// (React production, minified) into a private folder and `vite preview` on the same origin, with
// the same APIs. The predictive viewer is excluded from public bundles by design (it requires
// import.meta.env.DEV); its measurement build opens only that local research gate. These builds
// are written below data/interim/official/performance-v1/production/<label>/ and are never deployed.
// --after-warm waits, before the phase-2 operations, until the in-process alerts preload of the
// administrative API finished (/health/alerts "warm"); without it the viewer is measured while
// that preload still competes for the same process (worst case right after starting `dev`).
// --label NAME: every run writes ONLY into a new folder performance-v1/[production/]<NAME>/ (results.json,
// results.partial.json, build-*/); an existing folder stops the run before anything is written, so earlier
// results (F0 baseline, F2) are never emptied or overwritten. Without --label a timestamped name is used.
// --users 1 measures only the one-user level (harness check); the formal measurement keeps 1,5.
// Usage (repository root): node frontend/scripts/performance.browser.mjs [--reps 30] [--target production] [--label f2] [--users 1]
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { cpus, totalmem, release, platform } from 'node:os'
import { writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { developmentRuntime, portAvailable, startDevelopment } from './dev.mjs'
import { ALERTS_API, alertsRuntime } from './dev-alerts.mjs'
import { demoOfflineStyles } from './dev-demo.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const frontend = resolve(root, 'frontend')
const argument = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined
const target = argument('--target') || 'dev'
assert.ok(['dev', 'production'].includes(target), '--target admite dev o production')
const outputBase = resolve(root, 'data/interim/official/performance-v1', target === 'dev' ? '.' : 'production')
const origin = 'http://127.0.0.1:5173'
const reps = Number(process.argv[process.argv.indexOf('--reps') + 1]) || 30
// --only a,b re-measures selected operations (results file per run label).
const only = process.argv.includes('--only') ? new Set(process.argv[process.argv.indexOf('--only') + 1].split(',')) : null
const selected = name => !only || only.has(name)
const label = runLabel(argument('--label') || '')
const afterWarm = process.argv.includes('--after-warm')
const output = await newRunDirectory(outputBase, label)
// --users 1 (or 1,5) limits the concurrency levels, e.g. a one-user harness check.
const USERS = argument('--users') ? argument('--users').split(',').map(Number) : [1, 5]
assert.ok(USERS.length && USERS.every(n => Number.isInteger(n) && n >= 1 && n <= 5), '--users admite 1 a 5 (p. ej. 1 o 1,5)')
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

// Production: optimized bundles built before the environments start (build time is not measured).
async function buildBundle(name, { define, plugins = [] }) {
  const { build } = await import('vite')
  // Inside this run's new folder: no earlier build is ever emptied (emptyOutDir off).
  const outDir = resolve(output, `build-${name}`)
  await build({ root: frontend, configFile: join(frontend, 'vite.config.js'), plugins, define, logLevel: 'warn',
    build: { outDir, emptyOutDir: false } })
  return outDir
}
// One preview server on 5173 at a time, swapped between bundles while the APIs keep running.
let previewServer
async function servePreview(outDir) {
  const { preview } = await import('vite')
  await previewServer?.close()
  previewServer = await preview({ root: frontend, configFile: join(frontend, 'vite.config.js'), logLevel: 'warn',
    build: { outDir }, preview: { host: '127.0.0.1', port: 5173, strictPort: true } })
}
const previewRuntime = (base, outDir) => ({ ...base, async createVite() {
  await servePreview(outDir)
  return { listen: async () => {}, printUrls: () => {}, close: async () => { await previewServer?.close(); previewServer = undefined } }
} })

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

async function newPage(browser) {
  const context = await browser.createBrowserContext()
  const page = await context.newPage()
  page.setDefaultTimeout(SAMPLE_TIMEOUT_MS)
  await page.setViewport({ width: 1440, height: 1000 })
  // No request interception at all: with Puppeteer interception, and even with a CDP Fetch
  // pattern limited to the fixture API, Chromium intermittently failed concurrent requests to
  // the predictive API (net::ERR_FAILED within ~10 ms, before reaching it), leaving 10–80 % of
  // the 5-user viewer loads stuck until the 30 s limit. The app reaches the fixture API through
  // VITE_API_URL instead. Every external origin of the app is https (street tiles, web fonts,
  // links) and is blocked so the network outside this machine does not count.
  const cdp = await page.createCDPSession()
  await cdp.send('Network.enable')
  await cdp.send('Network.setBlockedURLs', { urls: ['https://*'] })
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
  for (const port of [5173, 8767]) assert.ok(await portAvailable(port), `El puerto ${port} debe estar libre`)
  // The fixture public API starts first: the frontend is pointed at it with VITE_API_URL.
  fixture = startFixture()
  const { port: fixturePort } = await fixture.ready
  const fixtureApi = `http://127.0.0.1:${fixturePort}`
  const bundles = {}
  if (target === 'production') {
    const publicApi = { 'import.meta.env.VITE_API_URL': JSON.stringify(fixtureApi) }
    bundles.public = await buildBundle('public', { define: publicApi })
    // Phase 2 (viewer and alerts panel) uses one bundle against the administrative API, like
    // `dev` (VITE_API_URL = 8767; a viewer bundle pointed at the stopped phase-1 fixture API
    // would add failed calls to every load).
    bundles.admin = await buildBundle('admin', { define: { 'import.meta.env.VITE_API_URL': JSON.stringify(ALERTS_API), 'import.meta.env.DEV': 'true' }, plugins: [demoOfflineStyles()] })
  }
  browser = await puppeteer.launch({ headless: true })
  const browserVersion = await browser.version()

  // Phase 1: dev + fixture public API.
  developmentRuntime.log = () => {}
  const devRuntime = { ...developmentRuntime, async createVite() {
    const { createServer } = await import('vite')
    return createServer({ root: frontend, configFile: join(frontend, 'vite.config.js'),
      define: { 'import.meta.env.SIGARD_PRIVATE_VIEW': 'false', 'import.meta.env.VITE_API_URL': JSON.stringify(fixtureApi) } })
  } }
  devSession = await startDevelopment(target === 'production' ? previewRuntime(developmentRuntime, bundles.public) : devRuntime)
  // Cold operations open a new browser context per sample; no state is shared between samples.
  const fresh = () => async () => ({})

  await measureOperation('actividad_carga_fixture', fresh(), async () => {
    const { page, close } = await newPage(browser)
    const ms = await timed(async () => {
      await page.goto(`${origin}/actividad`, { waitUntil: 'domcontentloaded' })
      await page.waitForFunction(() => document.querySelectorAll('.pa-map path.leaflet-interactive').length === 25 && document.querySelector('.pa-series .pa-bar'))
    }, page, 'actividad_carga_fixture')
    await close(); return ms
  })

  await measureOperation('prevencion_carga', fresh(), async () => {
    const { page, close } = await newPage(browser)
    const ms = await timed(async () => {
      await page.goto(`${origin}/prevencion`, { waitUntil: 'domcontentloaded' })
      await page.waitForFunction(() => document.querySelectorAll('.facility-marker').length === 27 && (document.querySelector('.prevention-content')?.textContent.length || 0) > 500)
    }, page, 'prevencion_carga')
    await close(); return ms
  })

  await fixture.stop(); fixture = undefined
  await devSession.stop(); await devSession.closed; devSession = undefined

  // Phase 2: `dev` runtime in session mode: administrative API with the predictive viewer
  // (protected values, administrator session) and the alerts panel.
  const alerts = alertsRuntime({ mode: 'session', source: 'local-research' })
  const runtime = target === 'production' ? previewRuntime(alerts, bundles.admin) : alerts
  runtime.announce = () => {}; runtime.log = () => {}
  alertsSession = await startDevelopment(runtime)
  let warmWaitMs = null
  if (afterWarm) {
    const start = performance.now()
    while (!(await (await fetch(`${ALERTS_API}/health/alerts`)).json()).warm) {
      assert.ok(performance.now() - start < 300000, 'la precarga de alertas no terminó en 5 minutos')
      await delay(500)
    }
    warmWaitMs = Math.round(performance.now() - start)
  }
  const { email, password } = alerts.service.credentials
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
  // One API login (same endpoint as /admin/reportes) for the viewer contexts.
  const login = await fetch(`${ALERTS_API}/api/v1/admin/session`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) })
  assert.equal(login.status, 200); token = (await login.json()).access_token
  const newViewerPage = async () => { const session = await newPage(browser); await session.page.evaluateOnNewDocument(value => sessionStorage.setItem('sigard_admin_token', value), token); return session }
  if (target === 'production') {
    // The measurement bundle must really contain the viewer (not the public map).
    const { page, close } = await newViewerPage()
    await page.goto(`${origin}/admin/predictivo`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.pv', { timeout: 120000 }); await close()
  }
  const visorReady = (page, timeout = SAMPLE_TIMEOUT_MS) => page.waitForFunction(() => document.querySelector('.pv')?.dataset.state === 'ready' && !document.querySelector('.pv-updating')
    && document.querySelectorAll('.pv-map path.leaflet-interactive').length >= 263, { timeout })
  await measureOperation('visor_carga', fresh(), async () => {
    const { page, close } = await newViewerPage()
    const ms = await timed(async () => { await page.goto(`${origin}/admin/predictivo`, { waitUntil: 'domcontentloaded' }); await visorReady(page) }, page, 'visor_carga')
    await close(); return ms
  })

  const loadedVisor = async () => {
    const session = await newViewerPage()
    await session.page.goto(`${origin}/admin/predictivo`, { waitUntil: 'domcontentloaded' }); await visorReady(session.page, 120000)
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
  await measureOperation('panel_alertas', loggedIn, async ({ page }) => {
    await page.goto(`${origin}/admin/reportes`, { waitUntil: 'domcontentloaded', timeout: 120000 })
    await page.waitForSelector('.admin-header', { timeout: 120000 })
    return timed(async () => {
      await (await page.waitForSelector('.admin-nav a[href="/admin/alertas"]')).click()
      await page.waitForFunction(() => document.querySelector('.alerts-banner') && document.querySelectorAll('.alerts-evaluate option').length > 0)
    }, page, 'panel_alertas')
  })

  const environment = {
    started_at: startedAt, finished_at: new Date().toISOString(), cpu: cpus()[0]?.model, logical_cores: cpus().length,
    ram_gb: Math.round(totalmem() / 2 ** 30), os: `${platform()} ${release()}`, node: process.version, browser: browserVersion,
    target, mode: target === 'dev'
      ? 'Vite dev server (sin bundle de producción), APIs locales uvicorn, Chromium headless en el mismo equipo; teselas y fuentes externas excluidas'
      : 'vite build (React de producción, minificado) + vite preview en 127.0.0.1:5173; mismas APIs locales; el bundle del visor abre sólo la compuerta de investigación local (DEV) para medirlo; teselas y fuentes externas excluidas',
    volume: '263 radios oficiales; visor con 208 semanas evaluables 2021–2024; actividad con fixture de 24 celdas + 1 fuera del área, 45 bloques',
    phase2_after_alerts_preload: afterWarm, alerts_preload_wait_ms: warmWaitMs,
    repetitions: reps, concurrency: USERS, percentile: 'p95 por rango más cercano', threshold_ms: THRESHOLD_MS,
  }
  await writeFile(resolve(output, only ? `results-${[...only].join('+')}.json` : 'results.json'), JSON.stringify({ environment, results, failures }, null, 2))
  console.log(JSON.stringify({ environment, all_pass: results.every(r => r.pass) }))
} finally {
  await browser?.close()
  await previewServer?.close()
  await fixture?.stop()
  if (devSession) { await devSession.stop(); await devSession.closed }
  if (alertsSession) { await alertsSession.stop(); await alertsSession.closed }
}
