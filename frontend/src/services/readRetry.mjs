// One automatic retry for read-only requests (initial page data).
// A GET that fails at the network level (fetch rejects with TypeError) or answers 5xx is sent
// once more after a short pause; the caller only sees an error if the retry fails too.
// Never retried: writes (POST/PATCH/PUT/DELETE), 4xx answers, user aborts and timeouts (a
// timeout already waited; retrying would double the wait).
export const RETRY_DELAY_MS = 500
const READ_METHODS = new Set(['GET', 'HEAD'])

function pause(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason)
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => { clearTimeout(timer); reject(signal.reason) }, { once: true })
  })
}

// A response whose body is not going to be read must be discarded: until its body is consumed or
// cancelled, Chromium keeps the request open and its HTTP/1.1 connection busy (6 per host). Probes
// that ignored the body of a 404 held connections to the local API until their 5 s timeout and
// queued the alerts panel behind them (F6.1).
export function discardBody(response) {
  try { response?.body?.cancel?.()?.catch?.(() => {}) } catch { /* already consumed or locked */ }
}

const networkFailure = (error, signal) => error?.name === 'TypeError' && !signal?.aborted

export async function fetchRead(url, options = {}, { fetcher = fetch, delay = RETRY_DELAY_MS } = {}) {
  if (!READ_METHODS.has((options.method || 'GET').toUpperCase())) return fetcher(url, options)
  let response
  try {
    response = await fetcher(url, options)
  } catch (error) {
    if (!networkFailure(error, options.signal)) throw error
    await pause(delay, options.signal)
    return fetcher(url, options)
  }
  if (response.status < 500) return response
  discardBody(response)
  await pause(delay, options.signal)
  return fetcher(url, options)
}
