// Administración v2 (F4): side menu and top bar around the existing screens.
// Owns its environment like test:alerts:browser: Vite (5173) + the local administrative API (8767)
// in session mode (disposable SQLite, generated admin kept in memory, fictional alerts source).
// The predictive viewer is fed by the generated fixture (intercepted), never by real aggregates.
//   default: menu tests (navigation, active item, keyboard, 390 px, session bar, context box,
//            counters) + screenshots of every Administración screen.
//   --capture-only --label antes: screenshots only, navigating the pre-F4 panels by their buttons.
// Screenshots (private): data/interim/official/ux-admin-v2-f4/<label>/<screen>-<desktop|mobile>.private.png
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { finalFixtureResponse } from '../security/predictive.fixture.mjs'
import { auditAccessibility } from './browser-a11y.mjs'
import { alertsRuntime, ALERTS_API } from './dev-alerts.mjs'
import { portAvailable, startDevelopment } from './dev.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const argument = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined
const captureOnly = process.argv.includes('--capture-only')
// --real: only the «Datos hasta» check against the real local predictive service (read-only, no screenshots).
const real = process.argv.includes('--real')
// A new folder per run label (--label or SIGARD_SHOTS_LABEL; timestamp by default); never overwritten.
const label = runLabel(argument('--label'))
const frontendRoot = fileURLToPath(new URL('..', import.meta.url))
const outputBase = resolve(frontendRoot, '..', 'data/interim/official/ux-admin-v2-f4')
let output
const origin = 'http://127.0.0.1:5173'
for (const port of [5173, 8767]) assert.ok(await portAvailable(port), `Port ${port} must be free; no existing service will be stopped`)

// Independent epidemiological-week calculation (Sunday–Saturday, week 1 holds 4 January).
function expectedWeek(iso) {
  const [y, m, d] = iso.split('-').map(Number), day = Date.UTC(y, m - 1, d)
  for (let year = y + 1; year >= y - 1; year--) {
    const jan4 = new Date(Date.UTC(year, 0, 4)), start = jan4.getTime() - jan4.getUTCDay() * 86400000
    if (start <= day) return `SE ${Math.floor((day - start) / 604800000) + 1}/${year}`
  }
}

const runtime = alertsRuntime({ mode: 'session', source: real ? 'local-research' : 'fictional' }); runtime.announce = () => {}
let environment = await startDevelopment(runtime)
const browser = await puppeteer.launch({ headless: true })
const errors = [], external = [], checks = []
const checkpoint = name => { checks.push(name); console.log(`✔ ${name}`) }
try {
  output = await newRunDirectory(outputBase, label)
  const { email, password } = runtime.service.credentials
  const page = await browser.newPage(); page.setDefaultTimeout(30000)
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()) })
  await page.setRequestInterception(true)
  page.on('request', r => {
    const u = new URL(r.url())
    if (!['http:', 'https:'].includes(u.protocol)) return r.continue()
    if (u.protocol === 'https:' && ['fonts.googleapis.com', 'fonts.gstatic.com'].includes(u.hostname)) return r.continue()
    if (/^[abc]\.tile\.openstreetmap\.org$/.test(u.hostname)) return r.abort() // offline map, as predictive.browser
    if (u.hostname !== '127.0.0.1' || !['5173', '8767'].includes(u.port)) { external.push(u.origin); return r.abort() }
    if (!real && u.pathname.startsWith('/api/v1/research/predictive/')) {
      const cors = { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Headers': 'Authorization, X-Sigard-Research', 'Access-Control-Allow-Methods': 'GET' }
      if (r.method() === 'OPTIONS') return r.respond({ status: 200, headers: cors })
      if (!(r.headers().authorization || '').startsWith('Bearer ')) return r.respond({ status: 401, contentType: 'application/json', headers: cors, body: '{"detail":"Autenticación administrativa requerida"}' })
      return r.respond({ status: 200, contentType: 'application/json', headers: cors, body: JSON.stringify(finalFixtureResponse(u.href)) })
    }
    return r.continue()
  })
  const settle = () => new Promise(done => setTimeout(done, 400))
  const noHorizontalScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)
  const shoot = async name => {
    for (const [kind, width] of [['desktop', 1440], ['mobile', 390]]) {
      await page.setViewport({ width, height: 1000 }); await settle()
      assert.ok(await noHorizontalScroll(), `${name} ${kind}: sin scroll horizontal`)
      await page.screenshot({ path: resolve(output, `${name}-${kind}.private.png`), fullPage: true })
    }
    await page.setViewport({ width: 1440, height: 1000 })
  }
  const clickButton = async text => {
    await page.waitForFunction(text => [...document.querySelectorAll('button')].some(b => b.textContent.trim() === text && !b.disabled), {}, text)
    await page.evaluate(text => [...document.querySelectorAll('button')].find(b => b.textContent.trim() === text && !b.disabled).click(), text)
  }
  const heading = text => page.waitForFunction(text => document.querySelector('.admin-header h1')?.textContent === text, {}, text)
  const viewerReady = () => page.waitForFunction(() => document.querySelector('.pv')?.dataset.state === 'ready')
  const login = async () => {
    await page.waitForSelector('.admin-login')
    await page.type('.admin-login input[type="email"]', email)
    await page.type('.admin-login input[type="password"]', password)
    await clickButton('Ingresar')
  }
  const alertsReady = () => page.waitForSelector('.alerts-tabs')
  await page.setViewport({ width: 1440, height: 1000 })

  // «Datos hasta» = the last week the viewer can show with data: read the same /calendar, compare
  // with the menu, check the SE independently from the date and open the viewer on that week.
  const checkViewerWeek = async () => {
    const token = await page.evaluate(() => sessionStorage.getItem('sigard_admin_token'))
    const calendar = await page.evaluate(async token => (await fetch('http://127.0.0.1:8767/api/v1/research/predictive/calendar',
      { headers: { 'X-Sigard-Research': 'local-read', Authorization: `Bearer ${token}` }, cache: 'no-store' })).json(), token)
    const available = calendar.weeks.filter(w => w.availability_status === 'available').sort((a, b) => a.target_week.localeCompare(b.target_week))
    const last = available.at(-1), expected = `SE ${last.target_epi_week}/${last.target_year}`
    assert.equal(expectedWeek(last.target_week), expected, 'SE del calendario coherente con su fecha')
    const menuWeek = () => page.waitForFunction(() => /visor/.test(document.querySelector('.admin-context [data-week]')?.dataset.weekSource || ''))
      .then(() => page.$eval('.admin-context [data-week]', e => e.textContent))
    assert.equal(await menuWeek(), expected, 'el menú muestra la última semana evaluable del visor')
    await page.goto(`${origin}/admin/predictivo?anio=${last.target_year}&se=${last.target_epi_week}`, { waitUntil: 'domcontentloaded' }); await viewerReady()
    assert.equal(await page.$eval('.pv', e => e.dataset.week), last.target_week, 'el visor abre esa semana')
    assert.equal(await menuWeek(), expected)
    return { expected, available: available.length }
  }

  if (real) {
    await page.goto(`${origin}/admin/inicio`, { waitUntil: 'networkidle0' }); await login(); await heading('Inicio')
    const week = await checkViewerWeek()
    checkpoint(`--real: «Datos hasta» ${week.expected} = última semana evaluable del visor (${week.available} semanas evaluables)`)
  } else if (captureOnly) {
    // Pre-F4 navigation: panels of /admin/reportes opened with their header buttons.
    await page.goto(`${origin}/admin/reportes`, { waitUntil: 'networkidle0' })
    await shoot('ingreso')
    await login(); await heading('Reportes ciudadanos'); await shoot('reportes')
    for (const [button, title, name, ready] of [['Alertas internas', 'Alertas internas', 'alertas', alertsReady],
      ['Contenido preventivo', 'Contenido preventivo', 'contenido'], ['Gestionar cuentas', 'Cuentas administrativas', 'cuentas']]) {
      await clickButton(button); await heading(title); if (ready) await ready(); await shoot(name)
      await clickButton('Volver a reportes'); await heading('Reportes ciudadanos')
    }
    await page.goto(`${origin}/admin/predictivo`, { waitUntil: 'domcontentloaded' }); await viewerReady(); await shoot('predictivo')
    checkpoint(`capturas ${label}`)
  } else {
    const nav = '.admin-nav'
    const activeItems = () => page.$$eval(`${nav} [aria-current="page"]`, items => items.map(item => item.getAttribute('href')))
    const SECTIONS = [
      ['/admin/inicio', 'Inicio', 'inicio'], ['/admin/predictivo', null, 'predictivo'], ['/admin/alertas', 'Alertas internas', 'alertas'],
      ['/admin/reportes', 'Reportes ciudadanos', 'reportes'], ['/admin/contenido', 'Contenido preventivo', 'contenido'],
      ['/admin/cuentas', 'Cuentas administrativas', 'cuentas'], ['/admin/auditoria', 'Auditoría', 'auditoria'],
    ]
    const ready = async (path, title) => {
      await page.waitForFunction(path => location.pathname === path, {}, path)
      if (path === '/admin/predictivo') await viewerReady(); else await heading(title)
      if (path === '/admin/alertas') await alertsReady()
    }

    // /admin → /admin/inicio; without a session the login (outside the frame) is shown.
    await page.goto(`${origin}/admin`, { waitUntil: 'networkidle0' })
    assert.equal(new URL(page.url()).pathname, '/admin/inicio')
    assert.equal(await page.$(nav), null, 'sin sesión no hay menú de Administración')
    await shoot('ingreso')
    await login(); await ready('/admin/inicio', 'Inicio')
    checkpoint('/admin lleva a /admin/inicio y el ingreso abre el marco')

    // Top bar: restricted area, session expiry, the administrator's email and logout.
    const bar = await page.$eval('.admin-topbar', e => e.textContent)
    assert.match(bar, /Área con acceso restringido/)
    assert.match(bar, /Sesión: vence en \d+ min/)
    assert.ok(bar.includes(email), 'el correo del administrador aparece en la barra superior')
    const minutes = Number(/vence en (\d+) min/.exec(bar)[1]); assert.ok(minutes >= 55 && minutes <= 60, `vencimiento razonable: ${minutes}`)
    checkpoint('barra superior: acceso restringido, vencimiento, correo y cerrar sesión')

    // Context box: environment, disclosure and «Datos hasta» = the viewer's last evaluable week.
    const context = await page.$eval('.admin-context', e => e.textContent)
    assert.match(context, /Entorno\s*Local/); assert.match(context, /Divulgación\s*Protegida/)
    assert.equal(await page.$eval('.admin-context [data-week]', e => getComputedStyle(e).fontFamily.includes('IBM Plex Mono')), true)
    const week = await checkViewerWeek()
    await page.goto(`${origin}/admin/inicio`, { waitUntil: 'networkidle0' }); await heading('Inicio')
    checkpoint(`caja de contexto: entorno, divulgación y «Datos hasta» ${week.expected} = última semana evaluable del visor`)

    // Groups and items, in the design's order; the Inicio and Auditoría placeholders.
    assert.deepEqual(await page.$$eval(`${nav} .admin-nav-group-title`, e => e.map(x => x.textContent)), ['Operación', 'Gestión'])
    assert.deepEqual(await page.$$eval(`${nav} a.admin-nav-item`, e => e.map(x => x.getAttribute('href'))), SECTIONS.map(s => s[0]))
    assert.match(await page.$eval('main', e => e.textContent), /Próximamente/)
    assert.equal(await page.$('.admin-header a[href="/admin/predictivo"]'), null, 'el botón «Módulo predictivo» del encabezado ya no existe')
    await shoot('inicio')

    // Mouse navigation: each item opens its screen and is the only aria-current item.
    for (const [path, title, name] of SECTIONS.slice(1)) {
      await page.click(`${nav} a[href="${path}"]`); await ready(path, title)
      assert.deepEqual(await activeItems(), [path], `ítem activo en ${path}`)
      const style = await page.$eval(`${nav} a[href="${path}"]`, e => getComputedStyle(e).backgroundColor)
      assert.equal(style, 'rgb(220, 238, 231)', 'ítem activo en menta (#dceee7)')
      if (path === '/admin/auditoria') assert.match(await page.$eval('main', e => e.textContent), /Próximamente/)
      const audit = await auditAccessibility(page, '.admin-shell')
      assert.deepEqual(audit.unnamed, [], `${path}: controles con nombre`); assert.deepEqual(audit.lowContrast, [], `${path}: contraste AA`)
      await shoot(name)
    }
    checkpoint('navegación del menú, ítem activo (aria-current) y contraste AA en cada pantalla')

    // Counters: only numbers the API returns (/alerts/status «pending», total of received reports).
    const token = await page.evaluate(() => sessionStorage.getItem('sigard_admin_token'))
    const api = (path, options = {}) => fetch(`${ALERTS_API}/api/v1/admin${path}`, { ...options, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
      .then(async response => { assert.ok(response.ok, `${path}: ${response.status}`); return response.json() })
    const badge = href => page.$eval(`${nav} a[href="${href}"]`, e => e.querySelector('.admin-nav-badge')?.textContent ?? null)
    const status = await api('/alerts/status')
    assert.equal(status.pending, 0); assert.equal(await badge('/admin/alertas'), null, 'sin candidatas no hay número')
    // Fictional source only: a rule over two generated radios and manual evaluations create pending candidates.
    const model = status.models.find(m => m.capability === 'quantity').id
    await api('/alerts/rules', { method: 'POST', body: JSON.stringify({ name: 'Contador ficticio', capability: 'quantity', model, radio_ids: ['FX0000001', 'FX0000002'], threshold: 5, consecutive_weeks: 1, enabled: true }) })
    for (const week of status.weeks.slice(-6)) {
      await api('/alerts/evaluations', { method: 'POST', body: JSON.stringify({ target_week: week.target_week }) })
      if ((await api('/alerts/status')).pending > 0) break
    }
    const pending = (await api('/alerts/status')).pending
    assert.ok(pending > 0, 'la fuente ficticia generó candidatas pendientes')
    const received = (await api('/citizen-reports?status=recibido&page_size=1')).total
    await page.click(`${nav} a[href="/admin/reportes"]`); await ready('/admin/reportes', 'Reportes ciudadanos')
    await page.waitForFunction((nav, n) => document.querySelector(`${nav} a[href="/admin/alertas"] .admin-nav-badge`)?.textContent === String(n), {}, nav, pending)
    assert.match(await page.$eval(`${nav} a[href="/admin/alertas"] .admin-nav-badge`, e => e.getAttribute('aria-label')), new RegExp(`^${pending} pendientes de revisión$`))
    assert.equal(await page.$eval(`${nav} a[href="/admin/alertas"] .admin-nav-badge`, e => getComputedStyle(e).backgroundColor), 'rgb(166, 74, 18)', 'contador en naranja (#a64a12)')
    assert.equal(await badge('/admin/reportes'), received ? String(received) : null)
    for (const href of ['/admin/inicio', '/admin/predictivo', '/admin/contenido', '/admin/cuentas', '/admin/auditoria']) assert.equal(await badge(href), null)
    await shoot('contadores')
    checkpoint(`contadores de la API (alertas pendientes ${pending}, reportes recibidos ${received}); sin número cuando la API da 0`)

    // Keyboard: Tab reaches the menu with a visible focus ring; Enter opens the item.
    await page.goto(`${origin}/admin/reportes`, { waitUntil: 'networkidle0' }); await heading('Reportes ciudadanos')
    await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0) })
    let reached = false
    for (let i = 0; i < 40 && !reached; i++) {
      await page.keyboard.press('Tab')
      reached = await page.evaluate(() => document.activeElement?.getAttribute('href') === '/admin/cuentas')
    }
    assert.ok(reached, 'Tab llega a «Cuentas» en el menú')
    const ring = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) } })
    assert.ok(ring.style !== 'none' && ring.width >= 2, `foco visible: ${JSON.stringify(ring)}`)
    await page.keyboard.press('Enter'); await ready('/admin/cuentas', 'Cuentas administrativas')
    assert.deepEqual(await activeItems(), ['/admin/cuentas'])
    checkpoint('teclado: Tab con foco visible y Enter abren el ítem')

    // Mobile 390 px: collapsible menu (button with aria-expanded), 44 px targets, no horizontal scroll.
    await page.setViewport({ width: 390, height: 900 }); await settle()
    assert.ok(await noHorizontalScroll())
    const toggle = '.admin-nav-toggle'
    assert.equal(await page.$eval(toggle, e => e.getAttribute('aria-expanded')), 'false')
    assert.equal(await page.$eval(`${nav} .admin-nav-items`, e => getComputedStyle(e).display), 'none', 'menú plegado en móvil')
    await page.click(toggle)
    assert.equal(await page.$eval(toggle, e => e.getAttribute('aria-expanded')), 'true')
    const sizes = await page.$$eval(`${nav} a.admin-nav-item, ${toggle}, .admin-topbar button`, e => e.map(x => [x.textContent.trim(), Math.round(x.getBoundingClientRect().height), Math.round(x.getBoundingClientRect().width)]))
    for (const [name, height, width] of sizes) assert.ok(height >= 44 && width >= 44, `área táctil de 44 px: ${name} ${width}×${height}`)
    assert.ok(await noHorizontalScroll())
    await page.screenshot({ path: resolve(output, 'menu-movil-abierto-mobile.private.png'), fullPage: true })
    await page.click(`${nav} a[href="/admin/contenido"]`); await ready('/admin/contenido', 'Contenido preventivo')
    assert.equal(await page.$eval(toggle, e => e.getAttribute('aria-expanded')), 'false', 'el menú se pliega al navegar')
    await page.setViewport({ width: 1440, height: 1000 })
    checkpoint('móvil 390 px: menú desplegable, áreas táctiles de 44 px y sin scroll horizontal')

    // Old and direct routes; logout from the top bar (also inside the viewer).
    await page.goto(`${origin}/admin/reportes`, { waitUntil: 'networkidle0' }); await heading('Reportes ciudadanos')
    await page.goto(`${origin}/admin/predictivo?anio=2024&se=12`, { waitUntil: 'domcontentloaded' }); await viewerReady()
    assert.equal(new URL(page.url()).search, '?anio=2024&se=12')
    assert.deepEqual(await activeItems(), ['/admin/predictivo'])
    await page.click('.admin-topbar .admin-logout')
    await page.waitForSelector('.admin-login'); assert.equal(await page.$(nav), null)
    assert.equal(await page.evaluate(() => sessionStorage.getItem('sigard_admin_token') ?? sessionStorage.getItem('sigard_admin_email')), null)
    assert.equal(new URL(page.url()).pathname, '/admin/predictivo')
    checkpoint('/admin/reportes y /admin/predictivo directos; «Cerrar sesión» de la barra limpia la sesión')

    // Session expiry clears the stored token AND the top-bar email: by the frame's timer at exp,
    // and when an expired token is found on arrival. Unsigned script-made tokens (never valid on the server).
    const fakeToken = exp => `e30.${Buffer.from(JSON.stringify({ sub: '0', role: 'admin', exp })).toString('base64url')}.FICTIONAL`
    const stored = () => page.evaluate(() => [sessionStorage.getItem('sigard_admin_token'), sessionStorage.getItem('sigard_admin_email')])
    const plant = (token, mail) => page.evaluate((token, mail) => { sessionStorage.setItem('sigard_admin_token', token); sessionStorage.setItem('sigard_admin_email', mail) }, token, mail)
    await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded' })
    await plant(fakeToken(Math.floor(Date.now() / 1000) + 6), 'vence@example.test')
    await page.goto(`${origin}/admin/inicio`, { waitUntil: 'domcontentloaded' }); await page.waitForSelector(nav)
    assert.ok((await page.$eval('.admin-topbar', e => e.textContent)).includes('vence@example.test'))
    await page.waitForSelector('.admin-login', { timeout: 20000 })
    assert.deepEqual(await stored(), [null, null], 'al vencer se borran token y correo')
    assert.match(await page.$eval('.admin-login', e => e.textContent), /La sesión venció/)
    await plant(fakeToken(Math.floor(Date.now() / 1000) - 60), 'vencido@example.test')
    await page.goto(`${origin}/admin/auditoria`, { waitUntil: 'domcontentloaded' }); await page.waitForSelector('.admin-login')
    await page.waitForFunction(() => sessionStorage.getItem('sigard_admin_email') === null)
    assert.deepEqual(await stored(), [null, null], 'un token vencido al llegar se borra con el correo')
    checkpoint('vencimiento: el marco borra token y correo (temporizador y token vencido al llegar)')

    // Public chrome: the site header links to /admin; / is the public home also in dev.
    await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded' })
    assert.equal(new URL(page.url()).pathname, '/')
    assert.equal(await page.$eval('.main-nav a[href="/admin"]', e => e.textContent), 'Administración')
    checkpoint('/ es la portada pública y «Administración» entra por /admin')
  }
  assert.deepEqual(errors, []); assert.deepEqual([...new Set(external)], [])
  const receipt = { status: 'passed', label, capture_only: captureOnly, source: 'generated_fictional_only', checks, browser_errors: errors }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify(receipt, null, 2))
} finally {
  await browser.close()
  if (environment) { await environment.stop(); await environment.closed; environment = undefined }
}
