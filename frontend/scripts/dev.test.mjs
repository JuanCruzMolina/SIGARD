import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { test } from 'node:test'
import { setTimeout as delay } from 'node:timers/promises'
import { identifyApi, portAvailable, spawnOwned, startDevelopment } from './dev.mjs'

const origin = 'http://127.0.0.1:5173'
const catalog = {
  schema_version: 'sigard-retrospective-spatial-score/1',
  models: [{ model_id: 'A', experiment_id: 'spatial_rf_05c_v1', training_version: 'official-spatial-rf-research-0.5c.0',
    weeks: Array.from({ length: 20 }, (_, i) => ({ target_week_start: `2024-01-${String(i + 1).padStart(2, '0')}`, target_epidemiological_week: i + 1 })) }],
}

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

test('reuses only an API with the existing contract and local access guard', async t => {
  const requests = []
  const { base } = await serverFor(t, (req, res) => {
    requests.push(req)
    res.setHeader('Content-Type', 'application/json')
    if (req.url === '/health') return res.end('{"status":"ok"}')
    if (req.headers.origin !== origin || req.headers['x-sigard-research'] !== 'local-read') {
      res.writeHead(403).end('{}')
      return
    }
    res.setHeader('Access-Control-Allow-Origin', origin)
    res.setHeader('Cache-Control', 'no-store, private')
    res.end(JSON.stringify(catalog))
  })
  assert.equal(await identifyApi(base), true)
  assert.equal(requests.length, 3)
  assert.ok(requests.every(req => !req.headers.cookie && !req.headers.authorization))
})

for (const kind of ['generic-health', 'wrong-contract', 'no-guard', 'redirect', 'blocked-artifacts']) {
  test(`rejects an existing service: ${kind}`, async t => {
    let requests = 0
    const { base } = await serverFor(t, (req, res) => {
      requests++
      if (kind === 'redirect') return res.writeHead(302, { Location: '/redirected' }).end()
      res.setHeader('Content-Type', 'application/json')
      if (req.url === '/health' || kind === 'generic-health') return res.end('{"status":"ok"}')
      if (kind === 'blocked-artifacts') return res.writeHead(503).end('{}')
      res.setHeader('Access-Control-Allow-Origin', origin)
      res.setHeader('Cache-Control', 'no-store, private')
      res.end(JSON.stringify(kind === 'wrong-contract' ? { ...catalog, schema_version: 'wrong' } : catalog))
    })
    assert.equal(await identifyApi(base), false)
    if (kind === 'redirect') assert.equal(requests, 1)
  })
}

function fixture({ external = false } = {}) {
  let resolveExit
  const calls = { start: 0, stop: 0, close: 0, listen: 0, ensure: 0, log: [] }
  const child = { exited: new Promise(resolve => { resolveExit = resolve }), stop: async () => { calls.stop++ } }
  const vite = { listen: async () => { calls.listen++ }, close: async () => { calls.close++ }, printUrls() {} }
  const runtime = {
    portAvailable: async port => port !== 8765 || !external,
    identifyApi: async () => true,
    ensurePython: async () => { calls.ensure++ },
    startApi: () => { calls.start++; return child },
    createVite: async () => vite,
    log: message => calls.log.push(message),
  }
  return { runtime, calls, vite, exit: resolveExit }
}

test('a reused API needs no virtualenv and survives shutdown', async () => {
  const { runtime, calls } = fixture({ external: true })
  const session = await startDevelopment(runtime)
  await session.stop()
  assert.equal(await session.closed, 0)
  assert.deepEqual([calls.ensure, calls.start, calls.stop, calls.close], [0, 0, 0, 1])
})

test('Ctrl+C closes only the owned API and Vite, once', async () => {
  const { runtime, calls } = fixture()
  const before = process.listenerCount('SIGINT')
  const session = await startDevelopment(runtime)
  process.emit('SIGINT')
  assert.equal(await session.closed, 0)
  await session.stop()
  assert.deepEqual([calls.ensure, calls.start, calls.stop, calls.close], [1, 1, 1, 1])
  assert.equal(process.listenerCount('SIGINT'), before)
})

test('busy frontend fails before starting Python or Vite', async () => {
  const { runtime, calls } = fixture()
  runtime.portAvailable = async () => false
  await assert.rejects(startDevelopment(runtime), /5173.*ocupado/)
  assert.equal(calls.start, 0)
  assert.equal(calls.listen, 0)
})

test('an unrelated service on 8765 is never stopped', async () => {
  const { runtime, calls } = fixture({ external: true })
  runtime.identifyApi = async () => false
  await assert.rejects(startDevelopment(runtime), /8765.*ocupado/)
  assert.deepEqual([calls.start, calls.stop, calls.close], [0, 0, 0])
})

test('missing virtualenv fails without starting either service', async () => {
  const { runtime, calls } = fixture()
  runtime.ensurePython = async () => { throw new Error('Falta backend/.venv') }
  await assert.rejects(startDevelopment(runtime), /backend\/\.venv/)
  assert.deepEqual([calls.start, calls.listen], [0, 0])
})

test('Vite startup failure closes the owned API', async () => {
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
  const { runtime, calls } = fixture()
  runtime.identifyApi = async () => false
  runtime.startApi = () => ({ exited: Promise.resolve({ code: 1 }), stop: async () => { calls.stop++ } })
  const session = await startDevelopment(runtime)
  assert.equal(await session.closed, 1)
  assert.equal(calls.listen, 0)
  assert.equal(calls.stop, 1)
})

test('interrupt while Vite is being created closes the late server', async () => {
  const { runtime, calls, vite } = fixture({ external: true })
  runtime.createVite = async () => {
    process.emit('SIGINT')
    await delay(1)
    return vite
  }
  const session = await startDevelopment(runtime)
  assert.equal(await session.closed, 0)
  assert.equal(calls.listen, 0)
  assert.ok(calls.close >= 1)
  assert.equal(calls.stop, 0)
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
