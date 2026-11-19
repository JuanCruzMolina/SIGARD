import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { test } from 'node:test'
import { proxyRequest } from './browser-proxy.mjs'

function fakeRequest(method, headers = {}, postData) {
  const calls = {}
  return { calls, method: () => method, headers: () => ({ host: '127.0.0.1:8000', ...headers }), postData: () => postData,
    respond: async value => { calls.respond = value }, abort: async reason => { calls.abort = reason } }
}

test('proxy answers with the exact fixture response, preflight and body included', async t => {
  const seen = []
  const server = createServer((req, res) => {
    let body = ''
    req.on('data', chunk => { body += chunk })
    req.on('end', () => {
      seen.push({ method: req.method, url: req.url, auth: req.headers.authorization, body, host: req.headers.host })
      const cors = { 'access-control-allow-origin': 'http://127.0.0.1:5173' }
      if (req.method === 'OPTIONS') { res.writeHead(204, { ...cors, 'access-control-allow-headers': 'Authorization' }); return res.end() }
      res.writeHead(req.method === 'POST' ? 201 : 200, { ...cors, 'content-type': 'application/json', 'cache-control': 'no-store' })
      res.end(JSON.stringify({ ok: true, method: req.method }))
    })
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(() => server.close())
  const base = `http://127.0.0.1:${server.address().port}`
  const get = fakeRequest('GET', { authorization: 'Bearer fictional-token', origin: 'http://127.0.0.1:5173' })
  await proxyRequest(get, `${base}/api/v1/admin/users?page=1`)
  assert.equal(get.calls.respond.status, 200)
  assert.equal(get.calls.respond.headers['access-control-allow-origin'], 'http://127.0.0.1:5173')
  assert.equal(get.calls.respond.headers['cache-control'], 'no-store')
  assert.equal(get.calls.respond.headers['content-length'], undefined)
  assert.deepEqual(JSON.parse(get.calls.respond.body), { ok: true, method: 'GET' })
  const preflight = fakeRequest('OPTIONS', { 'access-control-request-method': 'GET' })
  await proxyRequest(preflight, `${base}/api/v1/admin/users?page=1`)
  assert.equal(preflight.calls.respond.status, 204)
  const post = fakeRequest('POST', { 'content-type': 'application/json' }, '{"fictional":true}')
  await proxyRequest(post, `${base}/api/v1/admin/users`)
  assert.equal(post.calls.respond.status, 201)
  assert.deepEqual(seen.map(r => [r.method, r.url, r.body]), [['GET', '/api/v1/admin/users?page=1', ''], ['OPTIONS', '/api/v1/admin/users?page=1', ''], ['POST', '/api/v1/admin/users', '{"fictional":true}']])
  assert.equal(seen[0].auth, 'Bearer fictional-token')
  assert.notEqual(seen[0].host, '127.0.0.1:8000')
})

test('proxy aborts the page request when the fixture is unreachable', async () => {
  const request = fakeRequest('GET')
  await proxyRequest(request, 'http://127.0.0.1:9/unreachable')
  assert.equal(request.calls.abort, 'failed')
  assert.equal(request.calls.respond, undefined)
})
