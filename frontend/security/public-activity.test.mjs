import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { blockLabel, loadActivity, periodBanner, periodText, resetActivityCache, validateActivity } from '../src/services/publicActivity.mjs'

const frontend = fileURLToPath(new URL('../', import.meta.url))
const root = resolve(frontend, '..')

// Clearly fictional contract sample; unrelated to cartography or official sources.
function sample(changes = {}) {
  const block = (year, number, weeks, start, end, city) => ({ id: `${year}-B${String(number).padStart(2, '0')}`, year, block: number, weeks, start, end,
    radios: { 'FICT-001': 'bajo', 'FICT-002': 'protegido', 'FICT-003': 'alto' }, city_weeks: city })
  const blocks = [
    block(2020, 1, [1, 2, 3, 4], '2019-12-29', '2020-01-25', [{ year: 2020, week: 1, start: '2019-12-29', end: '2020-01-04', value: 6, display: null },
      { year: 2020, week: 2, start: '2020-01-05', end: '2020-01-11', value: null, display: '<5' }]),
    block(2020, 13, [49, 50, 51, 52, 53], '2020-11-29', '2021-01-02', [{ year: 2020, week: 53, start: '2020-12-27', end: '2021-01-02', value: null, display: 'oculto' }]),
    block(2024, 6, [21, 22, 23, 24], '2024-05-19', '2024-06-15', []),
  ]
  return { schema: 'sigard-public-activity/1', generated_at: '2026-11-16', geometry_source: 'inline', source: { kind: 'fixture', fictional: true },
    period: { first_block: '2020-B01', last_block: '2024-B06', start: '2019-12-29', end: '2024-06-15' }, outside_radios: ['FICT-900'], blocks, ...changes }
}

test('banner and covered period always come from the package', () => {
  const activity = validateActivity(sample())
  assert.equal(periodBanner(activity), 'Datos históricos: período SE 1–4/2020 a SE 21–24/2024. No reflejan la situación actual.')
  assert.equal(periodText(activity), 'Período cubierto: 29/12/2019 al 15/06/2024 (años 2020, 2024).')
  assert.equal(blockLabel(activity.blocks[1]), 'SE 49–53/2020')
})

test('contract rejects excluded years, overlaps, small or malformed city weeks and real-looking inline geometry', () => {
  const base = sample()
  const mutate = fn => { const copy = structuredClone(base); fn(copy); return copy }
  for (const invalid of [
    mutate(a => { a.blocks[0].year = 2022 }),
    mutate(a => { a.blocks[1].weeks = [4, 49] ; a.blocks[1].year = 2020 }),
    mutate(a => { a.blocks[0].city_weeks[0].value = 3 }),
    mutate(a => { a.blocks[0].city_weeks[1].display = null }),
    mutate(a => { a.blocks[0].radios['FICT-001'] = 7 }),
    mutate(a => { a.source.fictional = false }),
    mutate(a => { a.schema = 'other' }),
    mutate(a => { a.period.last_block = '2024-B05' }),
  ]) assert.throws(() => validateActivity(invalid), /inválido/)
})

test('view is disabled by default: 404, network failure or invalid package', async () => {
  const response = (status, body) => async () => ({ ok: status === 200, status, json: async () => body })
  resetActivityCache()
  assert.deepEqual(await loadActivity(response(404, { detail: 'no habilitado' })), { enabled: false })
  // A failure is still disabled for the public pages, but marked as unknown (Inicio: «No disponible»).
  for (const fetcher of [async () => { throw new Error('offline') }, response(200, { schema: 'x' }), response(500, {})]) {
    resetActivityCache()
    assert.deepEqual(await loadActivity(fetcher), { enabled: false, unavailable: true })
  }
  // A probe that never answers is aborted and fails closed instead of staying pending.
  resetActivityCache()
  const hanging = (url, options) => new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(options.signal.reason)))
  const started = Date.now()
  assert.deepEqual(await loadActivity(hanging, 50), { enabled: false, unavailable: true })
  assert.ok(Date.now() - started < 2000)
  resetActivityCache()
  const enabled = await loadActivity(response(200, sample()))
  assert.equal(enabled.enabled, true)
  resetActivityCache()
})

function files(folder) {
  if (!existsSync(folder)) return []
  return readdirSync(folder).flatMap(name => {
    const path = resolve(folder, name)
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}

test('no activity package is shipped in public or the built distribution', () => {
  const shipped = [...files(resolve(frontend, 'public')), ...files(resolve(frontend, 'dist'))]
  assert.ok(shipped.length > 0)
  const privateManifest = resolve(root, 'data/processed/official/public-activity-v1/manifest.json')
  const privateHashes = new Set()
  if (existsSync(privateManifest)) {
    const manifest = readFileSync(privateManifest)
    privateHashes.add(createHash('sha256').update(manifest).digest('hex'))
    for (const digest of Object.values(JSON.parse(manifest).files)) privateHashes.add(digest)
  }
  for (const path of shipped) {
    const data = readFileSync(path)
    assert.ok(!privateHashes.has(createHash('sha256').update(data).digest('hex')), `private package file shipped: ${path}`)
    if (/\.(json|geojson|txt|csv)$/i.test(path)) {
      const text = data.toString('utf8')
      assert.ok(!text.includes('sigard-public-activity'), `activity package data in ${path}`)
      assert.ok(!text.includes('city_weeks'), `activity series in ${path}`)
    }
    if (/\.js$/i.test(path)) {
      const text = data.toString('utf8')
      assert.ok(!text.includes('public-activity-v1') && !text.includes('public-activity-authorization'), `private path referenced in ${path}`)
      assert.ok(!/FICT-\d{3}/.test(text), `fictional fixture bundled in ${path}`)
    }
  }
})

test('the frontend reads activity only from the API, never from a bundled or private file', () => {
  const sources = files(resolve(frontend, 'src')).filter(p => /\.(jsx?|mjs)$/.test(p)).map(p => [p, readFileSync(p, 'utf8')])
  for (const [path, text] of sources) {
    assert.ok(!text.includes('data/processed') && !text.includes('data/interim'), `private data path in ${path}`)
  }
  const service = readFileSync(resolve(frontend, 'src/services/publicActivity.mjs'), 'utf8')
  assert.match(service, /\/api\/v1\/public\/activity/)
})
