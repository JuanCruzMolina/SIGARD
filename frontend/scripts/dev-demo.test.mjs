import assert from 'node:assert/strict'
import { test } from 'node:test'
import { access, readFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createDemoService, demoEnvironment, demoOfflineStyles, demoRuntime } from './dev-demo.mjs'
import { portAvailable, spawnOwned, startDevelopment } from './dev.mjs'

const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))))
const python = join(root, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')

test('demo removes the optional font request only from its own stylesheet in memory', async () => {
  const path = join(root, 'frontend/src/index.css')
  const source = await readFile(path, 'utf8')
  const plugin = demoOfflineStyles()
  assert.doesNotMatch(plugin.transform(source, path), /fonts.googleapis.com/)
  assert.equal(plugin.transform(source, join(root, 'frontend/src/App.css')), undefined)
  assert.equal(await readFile(path, 'utf8'), source)
})

test('demo child discards inherited DB, PostgreSQL, bootstrap and Python configuration', () => {
  const env = demoEnvironment({ DATABASE_URL: 'forbidden', PGHOST: 'forbidden', SIGARD_POSTGIS_URL: 'forbidden',
    SECRET_KEY: 'forbidden', ADMIN_BOOTSTRAP_PASSWORD: 'forbidden', PYTHONPATH: 'forbidden', PATH: 'required' })
  assert.deepEqual(env, { PATH: 'required', PYTHONIOENCODING: 'utf-8' })
})

test('Python isolation rejects persistent configuration/DB paths and geocoding with existing auth', async () => {
  const probe = spawnOwned(python, ['-I', '-B', join(root, 'backend/tests/demo_isolated.py')], { cwd: root, silent: true })
  let output = ''
  probe.stdout.resume()
  probe.stderr.on('data', data => { output += data })
  const result = await probe.exited
  assert.equal(result.code, 0, output)
})

test('fictional workspace validates roles, inputs, unknowns, alerts, revocation and production exclusion', async () => {
  const probe = spawnOwned(python, ['-I', '-B', join(root, 'backend/tests/demo_workspace_isolated.py')], { cwd: root, silent: true })
  let output = ''
  probe.stdout.resume()
  probe.stderr.on('data', data => { output += data })
  const result = await probe.exited
  assert.equal(result.code, 0, output)
})

test('demo explicitly opts out of starting or querying private A/B', async () => {
  const { runtime, calls, resolveReady } = fixture()
  runtime.research = demoRuntime().research
  runtime.identifyApi = () => assert.fail('Private research must not be queried')
  runtime.startApi = () => assert.fail('Private research must not be started')
  runtime.portAvailable = async port => { assert.notEqual(port, 8765); return true }
  resolveReady()
  const session = await startDevelopment(runtime)
  await session.stop()
  assert.equal(await session.closed, 0)
  assert.equal(calls.apiStart, 0)
})

function fixture() {
  const calls = { apiStop: 0, companionStop: 0, close: 0, apiStart: 0, listen: 0 }
  let resolveExit, resolveReady
  const ready = new Promise(resolve => { resolveReady = resolve })
  const companion = { ready, exited: new Promise(resolve => { resolveExit = resolve }), stop: async () => { calls.companionStop++ } }
  const runtime = {
    portAvailable: async () => true, identifyApi: async () => true, ensurePython: async () => {},
    startApi: () => { calls.apiStart++; return { exited: new Promise(() => {}), stop: async () => { calls.apiStop++ } } },
    startCompanion: () => companion,
    createVite: async () => ({ close: async () => { calls.close++ }, listen: async () => { calls.listen++ }, printUrls() {} }),
    log() {},
  }
  return { calls, runtime, companion, resolveExit, resolveReady }
}

test('extra requirements fail before starting either API', async () => {
  const { runtime, calls } = fixture()
  runtime.checkRequirements = async () => { throw new Error('8766 ocupado') }
  await assert.rejects(startDevelopment(runtime), /8766 ocupado/)
  assert.equal(calls.apiStart, 0)
})

test('real occupied demo port is rejected without connecting, spawning or killing', async t => {
  const listener = createServer(() => assert.fail('Must not connect to unknown service'))
  assert.ok(await portAvailable(8766), '8766 must be free for the isolation check')
  await new Promise(resolve => listener.listen(8766, '127.0.0.1', resolve))
  t.after(() => new Promise(resolve => listener.close(resolve)))
  await assert.rejects(demoRuntime().checkRequirements(), /8766.*ocupado/)
  assert.ok(listener.listening)
})

test('demo readiness failure cleans both owned APIs before any frontend is served', async () => {
  const { runtime, calls, companion } = fixture()
  companion.ready = Promise.reject(new Error('SQLite startup failed'))
  await assert.rejects(startDevelopment(runtime), /SQLite startup failed/)
  assert.deepEqual([calls.apiStop, calls.companionStop, calls.listen], [1, 1, 0])
})

test('Ctrl+C during companion startup waits then cleans late resources once', async () => {
  const { runtime, calls, resolveReady } = fixture()
  runtime.startCompanion = (() => {
    const original = runtime.startCompanion
    return () => { process.emit('SIGINT'); setTimeout(resolveReady, 5); return original() }
  })()
  const session = await startDevelopment(runtime)
  assert.equal(await session.closed, 0)
  assert.deepEqual([calls.apiStop, calls.companionStop, calls.listen], [1, 1, 0])
})

test('companion crash stops Vite and own API, leaving a reused research API alone', async () => {
  const { runtime, calls, resolveReady, resolveExit } = fixture()
  runtime.portAvailable = async port => port !== 8765
  resolveReady()
  const session = await startDevelopment(runtime)
  resolveExit({ code: 1 })
  assert.equal(await session.closed, 1)
  assert.deepEqual([calls.apiStart, calls.apiStop, calls.companionStop, calls.close], [0, 0, 1, 1])
})

test('Vite failure removes companion and owned research API', async () => {
  const { runtime, calls, resolveReady } = fixture()
  resolveReady()
  runtime.createVite = async () => { throw new Error('Vite failed') }
  await assert.rejects(startDevelopment(runtime), /Vite failed/)
  assert.deepEqual([calls.apiStop, calls.companionStop], [1, 1])
})

test('real SQLite persists reports in-session, deletes on stop and starts empty with fresh credentials', async t => {
  assert.ok(await portAvailable(8766), '8766 must be free; never attach to an existing demo')
  const first = createDemoService()
  t.after(() => first.stop())
  await first.ready
  const credentials = first.credentials
  const request = (path, options) => fetch(`http://127.0.0.1:8766/api/v1${path}`, options)
  const json = body => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const created = await request('/citizen-reports', json({ category: 'agua_acumulada', description: 'Ejemplo totalmente ficticio creado sólo para comprobar la demo.',
    latitude: -29.418, longitude: -66.856, privacy_accepted: true, privacy_notice_version: '2026-08-19' }))
  assert.equal(created.status, 201)
  const { tracking_code: code } = await created.json()
  assert.equal((await request(`/citizen-reports/status/${code}`)).status, 200)
  const login = await request('/admin/session', json(credentials))
  assert.equal(login.status, 200)
  const { access_token: token } = await login.json()
  await access(join(first.directory, 'demo.sqlite3'))
  await first.stop()
  await assert.rejects(access(first.directory), { code: 'ENOENT' })
  assert.ok(await portAvailable(8766))
  const second = createDemoService()
  t.after(() => second.stop())
  await second.ready
  assert.ok(second.credentials.password !== credentials.password)
  assert.ok(second.credentials.email !== credentials.email)
  assert.equal((await request(`/citizen-reports/status/${code}`)).status, 404)
  assert.equal((await request('/admin/citizen-reports', { headers: { Authorization: `Bearer ${token}` } })).status, 401)
  await second.stop()
  await assert.rejects(access(second.directory), { code: 'ENOENT' })
  assert.ok(await portAvailable(8766))
})

test('occupied-port race in the Python child fails safely and removes its own directory', async t => {
  const listener = createServer()
  await new Promise(resolve => listener.listen(8766, '127.0.0.1', resolve))
  t.after(() => new Promise(resolve => listener.close(resolve)))
  const service = createDemoService()
  t.after(() => service.stop())
  await assert.rejects(service.ready, /terminó antes/)
  await service.stop()
  await assert.rejects(access(service.directory), { code: 'ENOENT' })
  assert.ok(listener.listening)
})
