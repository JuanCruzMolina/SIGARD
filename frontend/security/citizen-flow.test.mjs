import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { insideReportArea, normalizeReportText, REPORT_BOUNDS } from '../src/services/citizenReportValidation.mjs'

const source = (await readFile(new URL('../src/services/citizenReports.js', import.meta.url), 'utf8'))
  .replaceAll('import.meta.env.VITE_API_URL', 'undefined')
const api = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)

test('report area accepts only finite city coordinates and preserves boundary points', () => {
  for (const point of [REPORT_BOUNDS[0], REPORT_BOUNDS[1], [-29.418, -66.856]]) assert.ok(insideReportArea(point))
  for (const point of [null, [], [NaN, 0], [-30, -66.856], [-29.418, -70], ['-29.4', -66.8]]) assert.equal(insideReportArea(point), false)
  assert.equal(normalizeReportText('  Agua   acumulada\n cerca de la plaza  '), 'Agua acumulada cerca de la plaza')
  assert.equal(normalizeReportText(' '.repeat(20)), '')
})

test('status request normalizes the code, propagates cancellation and avoids browser cache/credentials', async t => {
  const controller = new AbortController()
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.ok(url.endsWith('/status/SGD-RPT-ABC123'))
    assert.equal(options.signal, controller.signal)
    assert.equal(options.cache, 'no-store')
    assert.equal(options.credentials, 'omit')
    return new Response(JSON.stringify({ tracking_code: 'SGD-RPT-ABC123', status: 'recibido' }), { headers: { 'Content-Type': 'application/json' } })
  })
  assert.equal((await api.getCitizenReportStatus('  sgd-rpt-abc123 ', { signal: controller.signal })).status, 'recibido')
})

test('network errors offer recovery while intentional cancellation stays silent to callers', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('network') })
  await assert.rejects(api.getCitizenReportStatus('SGD-RPT-ABC123'), /Revisá la conexión/)
  fetch.mock.mockImplementation(async () => { throw new DOMException('cancelled', 'AbortError') })
  await assert.rejects(api.getCitizenReportStatus('SGD-RPT-ABC123'), { name: 'AbortError' })
})

test('filtered export sends the same filters as the listing and preserves authentication errors', async t => {
  const filters = { category: 'agua_acumulada', neighborhood: 'Zona Ficticia', date_from: '2030-01-01', date_to: '' }
  const urls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    urls.push(url)
    assert.equal(options.headers.Authorization, 'Bearer fictitious-token')
    return new Response('{}', { status: 403, headers: { 'Content-Type': 'application/json' } })
  })
  await assert.rejects(api.listAdminReports('fictitious-token', filters), error => error.status === 403)
  await assert.rejects(api.downloadAdminExport('fictitious-token', filters), error => error.status === 403)
  assert.equal(new URL(urls[0]).search, new URL(urls[1]).search)
  assert.equal(new URL(urls[1]).searchParams.get('neighborhood'), 'Zona Ficticia')
})
