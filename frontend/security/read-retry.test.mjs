// One automatic retry for initial read-only requests (P6.2). Fake fetchers only; no network.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fetchRead } from '../src/services/readRetry.mjs'
import { loadActivity, resetActivityCache } from '../src/services/publicActivity.mjs'

const ok = body => ({ ok: true, status: 200, json: async () => body })
const status = code => ({ ok: false, status: code, json: async () => ({ detail: 'FICTICIO' }) })
const offline = () => { throw new TypeError('Failed to fetch') }

// Plays the given outcomes in order and records every call.
function script(...outcomes) {
  const calls = []
  const fetcher = async (url, options) => {
    calls.push(options?.method || 'GET')
    const next = outcomes[calls.length - 1]
    return typeof next === 'function' ? next() : next
  }
  return { fetcher, calls }
}

test('a transient network failure or 5xx is retried once and the data arrives', async () => {
  for (const first of [offline, status(503), status(500)]) {
    const { fetcher, calls } = script(first, ok({ value: 'FICTICIO' }))
    const started = Date.now()
    const response = await fetchRead('http://127.0.0.1/x', {}, { fetcher, delay: 20 })
    assert.equal(response.status, 200)
    assert.deepEqual(await response.json(), { value: 'FICTICIO' })
    assert.equal(calls.length, 2)
    assert.ok(Date.now() - started >= 15, 'waits before retrying')
  }
})

test('two failures surface the error (only one retry)', async () => {
  const network = script(offline, offline, ok({}))
  await assert.rejects(fetchRead('http://127.0.0.1/x', {}, { fetcher: network.fetcher, delay: 1 }), TypeError)
  assert.equal(network.calls.length, 2)
  const server = script(status(502), status(503), ok({}))
  assert.equal((await fetchRead('http://127.0.0.1/x', {}, { fetcher: server.fetcher, delay: 1 })).status, 503)
  assert.equal(server.calls.length, 2)
})

test('4xx answers, writes, aborts and timeouts are never retried', async () => {
  for (const code of [400, 401, 403, 404, 409, 422, 429]) {
    const { fetcher, calls } = script(status(code), ok({}))
    assert.equal((await fetchRead('http://127.0.0.1/x', {}, { fetcher, delay: 1 })).status, code)
    assert.equal(calls.length, 1)
  }
  for (const method of ['POST', 'PATCH', 'PUT', 'DELETE', 'post']) {
    const failing = script(offline, ok({}))
    await assert.rejects(fetchRead('http://127.0.0.1/x', { method }, { fetcher: failing.fetcher, delay: 1 }), TypeError)
    assert.equal(failing.calls.length, 1, `${method} sent once`)
    const server = script(status(500), ok({}))
    assert.equal((await fetchRead('http://127.0.0.1/x', { method }, { fetcher: server.fetcher, delay: 1 })).status, 500)
    assert.equal(server.calls.length, 1, `${method} 5xx not retried`)
  }
  const controller = new AbortController(); controller.abort()
  const aborted = script(() => { throw Object.assign(new TypeError('aborted'), {}) }, ok({}))
  await assert.rejects(fetchRead('http://127.0.0.1/x', { signal: controller.signal }, { fetcher: aborted.fetcher, delay: 1 }))
  assert.equal(aborted.calls.length, 1)
  const timeout = script(() => { throw new DOMException('timeout', 'TimeoutError') }, ok({}))
  await assert.rejects(fetchRead('http://127.0.0.1/x', {}, { fetcher: timeout.fetcher, delay: 1 }), /timeout/)
  assert.equal(timeout.calls.length, 1)
})

test('public activity: a transient failure still shows the data; 404 stays disabled without retry', async () => {
  const valid = { schema: 'sigard-public-activity/1', generated_at: '2026-11-16', geometry_source: 'inline', source: { kind: 'fixture', fictional: true },
    period: { first_block: '2020-B01', last_block: '2020-B01', start: '2019-12-29', end: '2020-01-25' }, outside_radios: [],
    blocks: [{ id: '2020-B01', year: 2020, block: 1, weeks: [1, 2, 3, 4], start: '2019-12-29', end: '2020-01-25', radios: { 'FICT-001': 'bajo' }, city_weeks: [] }] }
  resetActivityCache()
  const transient = script(offline, ok(valid))
  assert.equal((await loadActivity(transient.fetcher)).enabled, true)
  assert.equal(transient.calls.length, 2)
  resetActivityCache()
  const twice = script(status(503), status(503))
  assert.deepEqual(await loadActivity(twice.fetcher), { enabled: false, unavailable: true })
  assert.equal(twice.calls.length, 2)
  resetActivityCache()
  const disabled = script(status(404), ok(valid))
  assert.deepEqual(await loadActivity(disabled.fetcher), { enabled: false })
  assert.equal(disabled.calls.length, 1)
  resetActivityCache()
})

test('every initial read goes through fetchRead; citizen writes keep their own method', () => {
  const source = name => readFileSync(new URL(`../src/services/${name}`, import.meta.url), 'utf8')
  const backtest = source('backtestResults.js')
  assert.match(backtest, /fetchRead\(`\$\{PREDICTIVE_API\}\$\{path\}`/)
  assert.doesNotMatch(backtest, /[^.\w]fetch\(/)
  assert.match(source('publicActivity.mjs'), /fetchRead\(`\$\{API_URL\}\/api\/v1\/public\/activity`/)
  assert.match(source('preventionData.js'), /await fetchRead\(path/)
  const citizen = source('citizenReports.js')
  // apiRequest serves the public prevention GET and the writes; fetchRead skips non-GET methods.
  assert.match(citizen, /async function apiRequest[\s\S]*?await fetchRead\(`\$\{API_URL\}\$\{path\}`/)
  assert.match(citizen, /export function getPublicPrevention[\s\S]*?apiRequest\('\/api\/v1\/public\/prevention'/)
  for (const write of ['createCitizenReport', 'updateAdminReport', 'createAdminAccount', 'deactivateAdminAccount', 'rotateAdminPassword']) {
    assert.match(citizen, new RegExp(`export function ${write}[\\s\\S]*?method: '(POST|PATCH)'`), `${write} declares its write method`)
  }
})
