// Forwards an intercepted page request to a loopback fixture API and answers it with the exact
// response (CORS preflights included). Rewriting the URL with request.continue({ url }) made
// Chromium intermittently fail a request with net::ERR_FAILED when another intercepted request
// was aborted at the same moment (for example on a panel change).
const HOP_BY_HOP = new Set(['content-length', 'content-encoding', 'transfer-encoding', 'connection'])

export async function proxyRequest(request, target) {
  try {
    const headers = { ...request.headers() }
    delete headers.host
    const method = request.method()
    const response = await fetch(target, { method, headers, body: ['GET', 'HEAD'].includes(method) ? undefined : request.postData(), redirect: 'manual' })
    const body = Buffer.from(await response.arrayBuffer())
    const responseHeaders = {}
    response.headers.forEach((value, key) => { if (!HOP_BY_HOP.has(key)) responseHeaders[key] = value })
    await request.respond({ status: response.status, headers: responseHeaders, body })
  } catch {
    await request.abort('failed').catch(() => {})
  }
}
