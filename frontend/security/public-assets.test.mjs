import assert from 'node:assert/strict'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { createServer, preview, resolveConfig } from 'vite'
import { approvedPublicAssets, assertApprovedDistribution, assertApprovedPublic, normalizedHash, publicAssetSafety, safetyMiddleware } from './public-assets.mjs'

const frontend = fileURLToPath(new URL('../', import.meta.url))
const temporary = resolve(frontend, '../ml/.tmp/security-node')
mkdirSync(temporary, { recursive: true })
function fixture() {
  const directory = mkdtempSync(resolve(temporary, 'fixture-'))
  mkdirSync(resolve(directory, 'data'))
  writeFileSync(resolve(directory, 'data/fictional.json'), '{"fictional":true}\n')
  writeFileSync(resolve(directory, 'favicon.svg'), '<svg/>\n')
  const approved = Object.fromEntries(['data/fictional.json', 'favicon.svg'].map((name) => [name, normalizedHash(resolve(directory, name))]))
  return { directory, approved }
}
function appFixture() {
  const root = mkdtempSync(resolve(temporary, 'app-'))
  for (const folder of ['public', 'dist']) {
    mkdirSync(resolve(root, folder, 'data'), { recursive: true })
    for (const name of Object.keys(approvedPublicAssets)) copyFileSync(resolve(frontend, 'public', name), resolve(root, folder, name))
  }
  writeFileSync(resolve(root, 'index.html'), '<!doctype html><title>Fictional security fixture</title>')
  writeFileSync(resolve(root, 'dist/index.html'), '<!doctype html><title>Fictional security fixture</title>')
  return root
}

test('all ten existing public resources and existing dist remain unchanged and approved', () => {
  assert.equal(Object.keys(approvedPublicAssets).length, 10)
  assert.equal(assertApprovedPublic(resolve(frontend, 'public')).approvedFiles, 10)
  assert.equal(assertApprovedDistribution(resolve(frontend, 'dist')).approvedFiles, 10)
})

test('actual application Vite config installs the security boundary', async () => {
  const config = await resolveConfig({ root: frontend, configFile: resolve(frontend, 'vite.config.js'), logLevel: 'silent' }, 'serve')
  assert.ok(config.plugins.some((plugin) => plugin.name === 'sigard-public-asset-safety'))
  assert.equal(config.server.fs.strict, true)
  assert.deepEqual(config.server.fs.allow, [frontend.replace(/\\/g, '/').replace(/\/$/, '')])
})

test('fictitious allowed resources are readable without modification', () => {
  const { directory, approved } = fixture()
  const before = readFileSync(resolve(directory, 'data/fictional.json'))
  assert.equal(assertApprovedPublic(directory, approved).approvedFiles, 2)
  assert.deepEqual(readFileSync(resolve(directory, 'data/fictional.json')), before)
})

test('unknown filenames are refused even without a private marker', () => {
  const { directory, approved } = fixture()
  writeFileSync(resolve(directory, 'data/ordinary.json'), '{"fictional":true}')
  assert.throws(() => assertApprovedPublic(directory, approved), /security check failed/)
  assert.equal(readFileSync(resolve(directory, 'data/ordinary.json'), 'utf8'), '{"fictional":true}')
})

test('replacement under an approved filename is refused', () => {
  const { directory, approved } = fixture()
  writeFileSync(resolve(directory, 'data/fictional.json'), '{"changed_fictional":true}')
  assert.throws(() => assertApprovedPublic(directory, approved), /security check failed/)
})

test('LF and CRLF remain equivalent across Git Windows and Linux checkouts', () => {
  const { directory, approved } = fixture()
  writeFileSync(resolve(directory, 'data/fictional.json'), '{"fictional":true}\r\n')
  assert.equal(assertApprovedPublic(directory, approved).approvedFiles, 2)
})

test('directory links are refused even if the files have approved names', () => {
  const { directory, approved } = fixture()
  const parent = mkdtempSync(resolve(temporary, 'links-'))
  symlinkSync(directory, resolve(parent, 'linked'), process.platform === 'win32' ? 'junction' : 'dir')
  assert.throws(() => assertApprovedPublic(resolve(parent, 'linked'), approved), /security check failed/)
})

test('middleware fails closed and never echoes a sensitive value', () => {
  let body, nextCalled = false
  const headers = {}
  const response = { setHeader: (name, value) => { headers[name] = value }, end: (value) => { body = value } }
  safetyMiddleware(() => { throw new Error('FICTIONAL_SENSITIVE_MARKER') })({}, response, () => { nextCalled = true })
  assert.equal(response.statusCode, 503)
  assert.equal(headers['Cache-Control'], 'no-store')
  assert.equal(nextCalled, false)
  assert.equal(body.includes('FICTIONAL_SENSITIVE_MARKER'), false)
})

test('middleware permits existing approved application responses', () => {
  let nextCalled = false
  safetyMiddleware(() => {})({}, {}, () => { nextCalled = true })
  assert.equal(nextCalled, true)
})

test('distribution rejects a stale or accidental private export', () => {
  const { directory, approved } = fixture()
  writeFileSync(resolve(directory, 'index.html'), '<!doctype html>')
  assertApprovedDistribution(directory, approved)
  writeFileSync(resolve(directory, 'data/fictional.private.json'), '{}')
  assert.throws(() => assertApprovedDistribution(directory, approved), /security check failed/)
})

test('build lifecycle blocks unapproved public source before building', () => {
  const plugin = publicAssetSafety()
  const root = appFixture()
  plugin.configResolved({ root, publicDir: resolve(root, 'public'), build: { outDir: 'dist' }, command: 'build' })
  writeFileSync(resolve(root, 'public/data/new-export.json'), '{"fictional":true}')
  assert.throws(() => plugin.buildStart(), /security check failed/)
})

test('build lifecycle checks its generated distribution', () => {
  const plugin = publicAssetSafety()
  const root = appFixture()
  plugin.configResolved({ root, publicDir: resolve(root, 'public'), build: { outDir: 'dist' }, command: 'build' })
  plugin.buildStart()
  plugin.closeBundle()
  writeFileSync(resolve(root, 'dist/data/new-export.json'), '{"fictional":true}')
  assert.throws(() => plugin.closeBundle(), /security check failed/)
})

test('actual Vite dev middleware blocks a fictitious file added after startup', async () => {
  const root = appFixture()
  const server = await createServer({ configFile: false, root, plugins: [publicAssetSafety()], server: { host: '127.0.0.1', port: 0 }, logLevel: 'silent' })
  try {
    await server.listen()
    const address = server.httpServer.address()
    const url = `http://127.0.0.1:${address.port}`
    const before = await fetch(url + '/data/available_weeks.json')
    assert.equal(before.status, 200)
    writeFileSync(resolve(root, 'public/data/new-export.json'), '{"FICTIONAL_SENSITIVE_MARKER":true}')
    const after = await fetch(url + '/data/new-export.json')
    assert.equal(after.status, 503)
    assert.equal((await after.text()).includes('FICTIONAL_SENSITIVE_MARKER'), false)
  } finally { await server.close() }
})

test('actual Vite preview middleware blocks a fictitious file added to dist', async () => {
  const root = appFixture()
  const server = await preview({ configFile: false, root, plugins: [publicAssetSafety()], preview: { host: '127.0.0.1', port: 0 }, logLevel: 'silent' })
  try {
    const address = server.httpServer.address()
    const url = `http://127.0.0.1:${address.port}`
    assert.equal((await fetch(url + '/data/available_weeks.json')).status, 200)
    writeFileSync(resolve(root, 'dist/data/new-export.json'), '{"FICTIONAL_SENSITIVE_MARKER":true}')
    const result = await fetch(url + '/data/new-export.json')
    assert.equal(result.status, 503)
    assert.equal((await result.text()).includes('FICTIONAL_SENSITIVE_MARKER'), false)
  } finally { await new Promise((resolveClose, reject) => server.httpServer.close((error) => error ? reject(error) : resolveClose())) }
})

test('Vite denies sensitive files outside public, including uppercase, and preserves approved GeoJSON', async () => {
  const root = appFixture()
  mkdirSync(resolve(root, 'exports'))
  const sensitivePaths = ['.ENV.backup', '.npmrc', 'settings.PRIVATE.yaml', 'exports/fictional.PARQUET', 'exports/coordinates.GEOJSON']
  for (const name of sensitivePaths) writeFileSync(resolve(root, name), 'FICTIONAL_SENSITIVE_MARKER')
  const server = await createServer({ configFile: false, root, plugins: [publicAssetSafety()], server: { host: '127.0.0.1', port: 0 }, logLevel: 'silent' })
  try {
    await server.listen()
    const url = `http://127.0.0.1:${server.httpServer.address().port}`
    assert.equal((await fetch(url + '/data/territorial_context.geojson')).status, 200)
    for (const name of sensitivePaths) {
      const response = await fetch(url + '/' + name + '?raw')
      assert.equal(response.status, 403)
      assert.equal((await response.text()).includes('FICTIONAL_SENSITIVE_MARKER'), false)
    }
  } finally { await server.close() }
})
