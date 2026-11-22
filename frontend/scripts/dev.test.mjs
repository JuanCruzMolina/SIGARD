import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { test } from 'node:test'
import { setTimeout as delay } from 'node:timers/promises'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { portAvailable, privateViewRequested, spawnOwned, startDevelopment } from './dev.mjs'
import { ALERTS_API, alertsRuntime, developmentDefine, GOOGLE_FONTS, PREDICTIVE_MISSING } from './dev-alerts.mjs'


async function serverFor(t, handler) {
  const server = createServer(handler)
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections() }))
  return { server, base: `http://127.0.0.1:${server.address().port}` }
}

test('detects occupied ports without closing their listener', async t => {
  const { server } = await serverFor(t, (_, res) => res.end())
  assert.equal(await portAvailable(server.address().port), false)
  assert.equal(server.listening, true)
  assert.equal(await portAvailable(0), true)
})

function fixture() {
  let resolveExit
  const calls = { start: 0, stop: 0, close: 0, listen: 0, ports: [], log: [] }
  const companion = { ready: Promise.resolve(), exited: new Promise(resolve => { resolveExit = resolve }), stop: async () => { calls.stop++ } }
  const vite = { listen: async () => { calls.listen++ }, close: async () => { calls.close++ }, printUrls() {} }
  const runtime = {
    portAvailable: async port => { calls.ports.push(port); return true },
    startCompanion: () => { calls.start++; return companion },
    createVite: async () => vite,
    log: message => calls.log.push(message),
  }
  return { runtime, calls, vite, companion, exit: resolveExit }
}

test('F2: dev never starts, probes or reuses a separate predictive API on 8765', async () => {
  const { runtime, calls } = fixture()
  const session = await startDevelopment(runtime)
  await session.stop()
  assert.equal(await session.closed, 0)
  assert.deepEqual(calls.ports, [5173])
  assert.deepEqual([calls.start, calls.stop, calls.close], [1, 1, 1])
  const source = await readFile(new URL('./dev.mjs', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /research_local|identifyApi|startApi/)
  assert.doesNotMatch(source.replace(/\/\/.*$/gm, ''), /8765/)
})

test('Ctrl+C closes only the owned administrative API and Vite, once', async () => {
  const { runtime, calls } = fixture()
  const before = process.listenerCount('SIGINT')
  const session = await startDevelopment(runtime)
  process.emit('SIGINT')
  assert.equal(await session.closed, 0)
  await session.stop()
  assert.deepEqual([calls.start, calls.stop, calls.close], [1, 1, 1])
  assert.equal(process.listenerCount('SIGINT'), before)
})

test('busy frontend fails before starting Python or Vite', async () => {
  const { runtime, calls } = fixture()
  runtime.portAvailable = async () => false
  await assert.rejects(startDevelopment(runtime), /5173.*ocupado/)
  assert.equal(calls.start, 0)
  assert.equal(calls.listen, 0)
})

test('failed requirements (virtualenv, 8767) start neither service', async () => {
  const { runtime, calls } = fixture()
  runtime.checkRequirements = async () => { throw new Error('Falta backend/.venv') }
  await assert.rejects(startDevelopment(runtime), /backend\/\.venv/)
  assert.deepEqual([calls.start, calls.listen], [0, 0])
})

test('Vite startup failure closes the owned administrative API', async () => {
  const { runtime, calls, vite } = fixture()
  vite.listen = async () => { throw new Error('EADDRINUSE:5173') }
  await assert.rejects(startDevelopment(runtime), /EADDRINUSE/)
  assert.equal(calls.stop, 1)
  assert.ok(calls.close >= 1)
})

test('unexpected Python exit shuts down Vite with a failure status', async () => {
  const { runtime, calls, exit } = fixture()
  const session = await startDevelopment(runtime)
  exit({ code: 1 })
  assert.equal(await session.closed, 1)
  assert.equal(calls.close, 1)
})

test('Python startup failure never starts Vite', async () => {
  const { runtime, calls, companion } = fixture()
  companion.ready = Promise.reject(new Error('La API administrativa terminó antes de estar lista.'))
  companion.ready.catch(() => {})
  await assert.rejects(startDevelopment(runtime), /API administrativa/)
  assert.equal(calls.listen, 0)
  assert.equal(calls.stop, 1)
})

test('interrupt while Vite is being created closes the late server', async () => {
  const { runtime, calls, vite } = fixture()
  runtime.createVite = async () => {
    process.emit('SIGINT')
    await delay(1)
    return vite
  }
  const session = await startDevelopment(runtime)
  assert.equal(await session.closed, 0)
  assert.equal(calls.listen, 0)
  assert.ok(calls.close >= 1)
  assert.equal(calls.stop, 1)
})

test('interrupt during listen waits for startup before closing Vite', async () => {
  const { runtime, vite } = fixture()
  let listening = false
  vite.listen = async () => {
    process.emit('SIGINT')
    await delay(1)
    listening = true
  }
  vite.close = async () => { listening = false }
  const session = await startDevelopment(runtime)
  assert.equal(await session.closed, 0)
  assert.equal(listening, false)
})

test('real owned process tree is terminated and an unrelated listener survives', async t => {
  const { server } = await serverFor(t, (_, res) => res.end())
  // A descendant reproduces Windows' virtualenv launcher -> Python process tree.
  const port = server.address().port
  const reservation = createServer()
  await new Promise(resolve => reservation.listen(0, '127.0.0.1', resolve))
  const childPort = reservation.address().port
  await new Promise(resolve => reservation.close(resolve))
  const owned = spawnOwned(process.execPath, ['-e', `
    const { spawn } = require('node:child_process');
    spawn(process.execPath, ['-e', "require('node:net').createServer().listen(${childPort}, '127.0.0.1')"], { stdio: 'ignore', windowsHide: true });
    setInterval(() => {}, 1000);
  `])
  t.after(() => owned.stop())
  const deadline = Date.now() + 5000
  while (await portAvailable(childPort)) {
    assert.ok(Date.now() < deadline, 'descendant did not start')
    await delay(50)
  }
  await owned.stop()
  await owned.stop()
  await owned.exited
  assert.equal(await portAvailable(childPort), true)
  assert.equal(await portAvailable(port), false)
})

test('private exact-values view requires the explicit SIGARD_PRIVATE_VIEW=1 opt-in', () => {
  assert.equal(privateViewRequested({}), false)
  for (const value of ['0', 'true', 'yes', 'on', ' 1', '']) assert.equal(privateViewRequested({ SIGARD_PRIVATE_VIEW: value }), false)
  assert.equal(privateViewRequested({ SIGARD_PRIVATE_VIEW: '1' }), true)
})

test('dev is the single entry point; dev:alerts is an alias and dev:demo is unchanged', async () => {
  const { scripts } = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'))
  assert.equal(scripts.dev, 'node scripts/dev.mjs')
  assert.equal(scripts['dev:alerts'], 'node scripts/dev.mjs')
  assert.equal(scripts['dev:demo'], 'node scripts/dev-demo.mjs')
  const entry = await readFile(new URL('./dev.mjs', import.meta.url), 'utf8')
  assert.match(entry, /startDevelopment\(alertsRuntime\(\)\)/)
})

test('the dev entry point loads its runtime without deadlocking the module cycle', async t => {
  // With 5173 taken, dev.mjs must load dev-alerts.mjs and fail fast on the port check,
  // before starting any API (a top-level await on that import hangs instead).
  const server = createServer((_, res) => res.end())
  const listening = await new Promise(resolve => { server.once('error', () => resolve(false)); server.listen(5173, '127.0.0.1', () => resolve(true)) })
  if (!listening) return t.skip('5173 ocupado; no se detiene ningún servicio existente')
  t.after(() => new Promise(resolve => server.close(resolve)))
  const child = spawnOwned(process.execPath, [fileURLToPath(new URL('./dev.mjs', import.meta.url))], { silent: true })
  let stderr = ''
  child.stdout.resume(); child.stderr.on('data', data => { stderr += data })
  const result = await Promise.race([child.exited, delay(20000, null)])
  if (!result) await child.stop()
  assert.ok(result, 'dev.mjs did not finish: module cycle deadlock')
  assert.equal(result.code, 1)
  assert.match(stderr, /5173 está ocupado/)
  assert.doesNotMatch(stderr, /unsettled top-level await/)
})

test('dev keeps SIGARD_PRIVATE_VIEW opt-in and points the admin area to 8767', () => {
  assert.deepEqual(developmentDefine({}), { 'import.meta.env.SIGARD_PRIVATE_VIEW': 'false', 'import.meta.env.VITE_API_URL': JSON.stringify(ALERTS_API) })
  assert.equal(developmentDefine({ SIGARD_PRIVATE_VIEW: '1' })['import.meta.env.SIGARD_PRIVATE_VIEW'], 'true')
  assert.equal(developmentDefine({ SIGARD_PRIVATE_VIEW: 'true' })['import.meta.env.SIGARD_PRIVATE_VIEW'], 'false')
})

// Fake administrative API (Node, not Python) that answers the coordinator handshake on 8767.
const fakeAdminApi = (admin, predictive = true) => `
const http = require('node:http')
const server = http.createServer((req, res) => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ alerts: true, session: 'fake-session' })) })
server.listen(8767, '127.0.0.1', () => console.log(JSON.stringify({ session: 'fake-session', storage: 'persistent-private-sqlite', admin: ${admin}, predictive: ${predictive} })))
process.stdin.on('data', () => server.close(() => process.exit(0)))`

for (const [admin, predictive] of [[false, true], [true, true], [true, false]]) {
  test(`dev starts the administrative API ${admin ? 'with' : 'without'} a local account${predictive ? '' : ' and an unverifiable predictive module'} and never creates one`, async t => {
    if (!await portAvailable(8767)) return t.skip('8767 ocupado; no se detiene ningún servicio existente')
    const launched = []
    const runtime = alertsRuntime({ launch: (args, options) => { launched.push(args); return spawnOwned(process.execPath, ['-e', fakeAdminApi(admin, predictive)], options) } })
    const service = runtime.startCompanion()
    t.after(() => service.stop())
    await service.ready
    assert.deepEqual(launched.map(args => args.slice(3)), [['serve']])
    assert.equal(service.adminMissing, !admin)
    assert.equal(service.credentials, undefined)
    const logs = []
    const original = console.log
    console.log = message => logs.push(String(message))
    try { runtime.announce() } finally { console.log = original }
    const hint = logs.filter(line => line.includes('alerts_local.py create-admin'))
    assert.equal(hint.length, admin ? 0 : 1)
    assert.equal(service.predictiveMissing, !predictive)
    assert.equal(logs.filter(line => line.includes(PREDICTIVE_MISSING)).length, predictive ? 0 : 1)
    assert.ok(logs.some(line => /VISOR PREDICTIVO: \/admin\/predictivo.*sesión de administrador.*\/mapa es siempre el mapa público/.test(line)))
    assert.ok(logs.every(line => !line.includes('8765')), 'no separate predictive API is announced')
    assert.ok(logs.every(line => !/contraseña:|password/i.test(line)), 'never prints a password')
    await service.stop()
    assert.equal(await portAvailable(8767), true)
  })
}

test('dev serves the Google Fonts stylesheet (IBM Plex Sans) like before F1, and no other external origin', async t => {
  // Regression: F1 inherited dev:demo's offline-styles plugin and dev lost IBM Plex Sans.
  const vite = await alertsRuntime().createVite()
  t.after(() => vite.close())
  const css = (await vite.transformRequest('/src/index.css')).code
  assert.match(css, /@import url\('https:\/\/fonts\.googleapis\.com\/css2\?family=IBM\+Plex\+Sans/)
  assert.match(css, /:root \{ font-family: 'IBM Plex Sans', sans-serif;/)
  const origins = new Set([...css.matchAll(/https:\/\/([a-z0-9.-]+)/g)].map(match => match[1]))
  assert.deepEqual([...origins].filter(host => !GOOGLE_FONTS.includes(host)), [])
})
