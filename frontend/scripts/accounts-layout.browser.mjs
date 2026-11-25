// Administración v2 · Cuentas (F6.5): visual states of the redesigned screen.
// Own environment: the disposable SQLite API of backend/tests/browser_admin_fixture.py (one
// fictitious administrator, no .env, no PostgreSQL) and its own Vite (5174) pointed straight at it,
// so no DevTools request interception is needed (it is on only for the «API error» state, a GET:
// with interception Chromium sometimes cancels a CORS-preflighted POST; see inventario.md).
//   states: list, new account, password change (form and result), deactivation with explicit
//   confirmation, deactivated account (no actions: the API has no reactivation), last active
//   administrator still blocked (UI and API 409), API error; desktop 1440 and mobile 390; AA,
//   keyboard, 44 px, texts ≥ 14 px. Secrets: no password, hash or token in the DOM at any capture.
// --before: captures only (selectors shared with the previous design), no layout assertions.
// Screenshots (private): data/interim/official/ux-admin-v2-f6-5/<label>/cuentas-<state>-<desktop|mobile>.private.png
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { auditAccessibility, tabReaches } from './browser-a11y.mjs'
import { portAvailable, spawnOwned } from './dev.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const argument = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined
const before = process.argv.includes('--before')
const label = runLabel(argument('--label'))
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const outputBase = resolve(root, 'data/interim/official/ux-admin-v2-f6-5')
const origin = 'http://127.0.0.1:5174'
assert.ok(await portAvailable(5174), 'Port 5174 must be free; no existing service will be stopped')

// Fictitious credentials of this run only (the fixture's administrator and the ones created here).
const ADMIN = { email: 'stage14-admin@example.test', password: 'fictitious-initial-password' }
const SECOND = { email: 'f65-segunda@example.test', password: 'fictitious-second-password', rotated: 'fictitious-rotated-password' }
const SECRETS = [ADMIN.password, SECOND.password, SECOND.rotated]

const env = { ...process.env, SIGARD_BROWSER_FRONTEND_URL: origin }
for (const key of Object.keys(env)) if (key.startsWith('PG') || key.startsWith('SIGARD_POSTGIS') || key === 'SIGARD_TEST_POSTGRES_URL') delete env[key]
const fixture = spawn(resolve(root, 'backend/.venv/Scripts/python.exe'), ['-B', 'backend/tests/browser_admin_fixture.py'], { cwd: root, env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] })
const closed = new Promise(done => fixture.once('exit', done))
let fixtureErrors = ''
fixture.stderr.on('data', chunk => { fixtureErrors += chunk.toString() })
let browser, vite
const errors = [], external = [], checks = []
const checkpoint = text => { const name = before ? `captura (sin aserciones de diseño): ${text}` : text; checks.push(name); console.log(`✔ ${name}`) }
try {
  const ready = await new Promise((done, reject) => {
    let buffer = ''
    const timer = setTimeout(() => reject(new Error('Disposable API did not start')), 15000)
    fixture.once('exit', () => reject(new Error(`Disposable API exited: ${fixtureErrors}`)))
    fixture.stdout.on('data', chunk => { buffer += chunk.toString(); if (buffer.includes('\n')) { clearTimeout(timer); done(JSON.parse(buffer.split('\n')[0])) } })
  })
  assert.equal(ready.postgis, false)
  const api = `http://127.0.0.1:${ready.port}`
  vite = spawnOwned(process.execPath, ['frontend/node_modules/vite/bin/vite.js', 'frontend', '--host', '127.0.0.1', '--port', '5174', '--strictPort'], { cwd: root, env: { ...env, VITE_API_URL: api } })
  for (let attempt = 0; attempt < 150; attempt++) { try { if ((await fetch(origin)).ok) break } catch { /* owned Vite starting */ } await delay(100) }

  const output = await newRunDirectory(outputBase, label)
  browser = await puppeteer.launch({ headless: true, args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'] })
  const page = await browser.newPage(); page.setDefaultTimeout(20000)
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()) })
  page.on('request', r => { const u = new URL(r.url()); if (/^https?:$/.test(u.protocol) && u.hostname !== '127.0.0.1') external.push(u.origin) })
  let failList = false
  const onIntercepted = r => {
    const u = new URL(r.url())
    if (failList && r.method() === 'GET' && u.pathname === '/api/v1/admin/users')
      return r.respond({ status: 503, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': origin }, body: '{"detail":"API ficticia temporalmente no disponible."}' })
    return r.continue()
  }

  const settle = (ms = 400) => delay(ms)
  const noHorizontalScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)
  let token = ''
  // No password, password hash or token anywhere in the page (markup and form values).
  const assertNoSecrets = async name => {
    const page_ = await page.evaluate(() => document.documentElement.outerHTML + [...document.querySelectorAll('input')].map(i => i.value).join('|'))
    const leaked = [...SECRETS, ...(token ? [token] : [])].filter(secret => page_.includes(secret))
    assert.deepEqual(leaked.map(s => `${s.slice(0, 6)}…`), [], `${name}: secretos en el DOM`)
    assert.ok(!/\$2[aby]\$\d\d\$|\$argon2|pbkdf2[_:$]/i.test(page_), `${name}: sin hashes en el DOM`)
    assert.ok(await page.$$eval('input[name="password"], input[name="confirmation"], input[name="current_password"]', l => l.every(i => i.type === 'password')), `${name}: campos de contraseña type=password`)
  }
  const shoot = async (name, widths = [['desktop', 1440], ['mobile', 390]]) => {
    await assertNoSecrets(name)
    for (const [kind, width] of widths) {
      await page.setViewport({ width, height: 1000 }); await settle()
      assert.ok(await noHorizontalScroll(), `${name} ${kind}: sin scroll horizontal`)
      if (!before) assert.ok(await page.$eval('.account-list', e => { const box = e.querySelector('.ui-table-scroll'); return !box || box.scrollWidth <= box.clientWidth + 1 }), `${name} ${kind}: la tabla entra en su tarjeta`)
      await page.screenshot({ path: resolve(output, `cuentas-${name}-${kind}.private.png`), fullPage: true })
    }
    await page.setViewport({ width: 1440, height: 1000 }); await settle(200)
  }
  const clickText = async (text, scope = 'main') => {
    await page.waitForFunction((text, scope) => [...document.querySelector(scope).querySelectorAll('button')].some(b => b.textContent.trim() === text && !b.disabled), {}, text, scope)
    await page.evaluate((text, scope) => [...document.querySelector(scope).querySelectorAll('button')].find(b => b.textContent.trim() === text && !b.disabled).click(), text, scope)
  }
  const fill = async (selector, value) => { await page.click(selector, { count: 3 }); await page.keyboard.press('Backspace'); if (value) await page.type(selector, value) }
  const listed = () => page.waitForFunction(() => document.querySelector('.account-list')?.getAttribute('aria-busy') === 'false' && document.querySelector('.account-list tbody'))
  const notice = text => page.waitForFunction(text => document.querySelector('.account-notice')?.textContent.includes(text), {}, text)
  const submit = async ({ next, current = ADMIN.password, confirm = true } = {}) => {
    if (next) { await fill('.account-operation input[name="password"]', next); await fill('.account-operation input[name="confirmation"]', next) }
    await fill('.account-operation input[name="current_password"]', current)
    if (confirm) await page.click('.account-operation input[name="confirmed"]')
    await page.click('.account-operation button[type="submit"]')
  }
  const mobileChecks = async name => {
    if (before) return
    await page.setViewport({ width: 390, height: 900 }); await settle()
    assert.ok(await noHorizontalScroll(), `${name}: sin scroll horizontal en 390 px`)
    const targets = await page.$$eval('main button, main a[href], main textarea, main input:not([type="checkbox"])', e => e
      .filter(x => x.checkVisibility() && x.getBoundingClientRect().width > 0)
      .map(x => { const r = x.getBoundingClientRect(); return [x.getAttribute('aria-label') || x.textContent.trim().slice(0, 30) || x.name || x.tagName, Math.round(r.width), Math.round(r.height)] })
      .filter(([, w, h]) => w < 44 || h < 44))
    assert.deepEqual(targets, [], `${name}: áreas táctiles de 44 px: ${JSON.stringify(targets)}`)
    const checkbox = await page.$$eval('main .account-confirm', l => l.filter(x => x.checkVisibility()).map(x => Math.round(x.getBoundingClientRect().height)))
    assert.ok(checkbox.every(h => h >= 44), `${name}: la confirmación (casilla y texto) mide al menos 44 px: ${checkbox}`)
    const small = await page.evaluate(() => {
      const found = [], walker = document.createTreeWalker(document.querySelector('main'), NodeFilter.SHOW_TEXT)
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const e = node.parentElement
        if (!node.textContent.trim() || !e.checkVisibility() || e.closest('svg, option')) continue
        const size = parseFloat(getComputedStyle(e).fontSize); if (size < 14) found.push(`${node.textContent.trim().slice(0, 30)} (${size} px, ${e.className || e.tagName})`)
      }
      return [...new Set(found)]
    })
    assert.deepEqual(small, [], `${name}: textos ≥ 14 px: ${JSON.stringify(small)}`)
    const audit = await auditAccessibility(page, 'main')
    assert.deepEqual(audit.unnamed, [], `${name}: controles con nombre (390)`); assert.deepEqual(audit.lowContrast, [], `${name}: contraste AA (390)`)
    await page.setViewport({ width: 1440, height: 1000 }); await settle(200)
  }
  const desktopAudit = async name => {
    if (before) return
    const audit = await auditAccessibility(page, 'main')
    assert.deepEqual(audit.unnamed, [], `${name}: controles con nombre (1440)`); assert.deepEqual(audit.lowContrast, [], `${name}: contraste AA (1440)`)
  }
  const deactivateViaApi = async (id, password) => fetch(`${api}/api/v1/admin/users/${id}/deactivate`, { method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: password }) })
  await page.setViewport({ width: 1440, height: 1000 })

  // 1. List with the only (own) administrator: «Desactivar» blocked in the screen and in the API.
  await page.goto(`${origin}/admin/cuentas`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.admin-login')
  await page.type('.admin-login input[type="email"]', ADMIN.email); await page.type('.admin-login input[type="password"]', ADMIN.password)
  await page.click('.admin-login button'); await listed()
  token = await page.evaluate(() => sessionStorage.getItem('sigard_admin_token'))
  assert.equal(await page.$$eval('.account-list tbody tr', r => r.length), 1)
  assert.equal(await page.$eval(`button[aria-label="Desactivar ${ADMIN.email}"]`, b => b.disabled), true, 'el último administrador activo no se puede desactivar desde la pantalla')
  const self = await (await fetch(`${api}/api/v1/admin/users`, { headers: { Authorization: `Bearer ${token}` } })).json()
  const blocked = await deactivateViaApi(self.current_user_id, ADMIN.password)
  assert.equal(blocked.status, 409, 'la API sigue bloqueando la desactivación del último administrador')
  assert.match((await blocked.json()).detail, /última cuenta administrativa activa/)
  if (!before) {
    assert.deepEqual(await page.$$eval('.ui-breadcrumb a', a => a.map(x => [x.textContent, x.getAttribute('href')])), [['Inicio', '/admin/inicio']])
    assert.equal(await page.$eval('.admin-header h1', e => e.textContent), 'Cuentas administrativas')
    assert.ok(await page.$('.admin-header .ui-button-primary'), '«Crear cuenta» en el encabezado')
    assert.deepEqual(await page.$$eval('.account-list thead th', t => t.map(x => x.textContent)), ['Correo', 'Estado', 'Creada', 'Acciones'])
    const row = await page.$eval('.account-list tbody tr', r => ({ self: r.querySelector('.account-self')?.textContent, state: r.querySelector('.account-state')?.textContent,
      icon: Boolean(r.querySelector('.account-state svg')), created: r.querySelector('time')?.getAttribute('datetime') }))
    assert.deepEqual([row.self, row.state, row.icon], ['Tu cuenta', 'Activa', true])
    assert.ok(row.created && !Number.isNaN(Date.parse(row.created)), 'fecha de alta real (created_at)')
    assert.match(await page.$eval('.account-policy', e => e.textContent), /Debe quedar al menos una cuenta administrativa activa/)
  }
  await desktopAudit('lista'); await shoot('lista'); await mobileChecks('lista')
  checkpoint('lista con la única cuenta: «Tu cuenta», insignia «Activa»; «Desactivar» bloqueado en la pantalla y la API responde 409')

  // 2. New account (current password + explicit confirmation).
  await clickText('Crear cuenta', before ? 'main' : '.admin-header')
  await page.waitForSelector('.account-operation input[name="email"]')
  assert.ok(await page.$$eval('.account-operation input[type="password"]', l => l.every(i => i.value === '' && ['new-password', 'current-password'].includes(i.autocomplete))), 'campos vacíos con autocomplete adecuado')
  await desktopAudit('alta'); await shoot('alta'); await mobileChecks('alta')
  await fill('.account-operation input[name="email"]', SECOND.email)
  await submit({ next: SECOND.password })
  await notice('creada'); await listed()
  await page.waitForFunction(() => document.querySelectorAll('.account-list tbody tr').length === 2)
  checkpoint('alta: formulario vacío con autocomplete, contraseña actual y confirmación; cuenta creada')

  // 3. Password change of the other account: form with its warning, then the result.
  await page.click(`button[aria-label="Rotar contraseña de ${SECOND.email}"]`)
  await page.waitForSelector('.account-operation input[name="confirmation"]')
  assert.match(await page.$eval('.account-operation', e => e.textContent), /La contraseña anterior dejará de funcionar\. Se invalidarán todos sus tokens anteriores\./)
  await desktopAudit('cambio de contraseña'); await shoot('cambio-contrasena'); await mobileChecks('cambio de contraseña')
  await submit({ next: SECOND.rotated })
  await notice('Contraseña actualizada'); await listed()
  await assertNoSecrets('contraseña cambiada')
  checkpoint('cambio de contraseña: aviso de invalidación de sesiones, confirmación y resultado sin mostrar la contraseña')

  // 4. Deactivation: without the explicit confirmation it does not proceed; then it does.
  await page.click(`button[aria-label="Desactivar ${SECOND.email}"]`)
  await page.waitForSelector('.account-operation input[name="current_password"]')
  assert.match(await page.$eval('.account-operation', e => e.textContent), /La cuenta dejará de poder ingresar\. Se invalidarán todos sus tokens anteriores\./)
  await desktopAudit('confirmación de desactivación'); await shoot('desactivacion-confirmacion'); await mobileChecks('confirmación de desactivación')
  await page.$eval('.account-operation input[name="confirmed"]', e => e.removeAttribute('required')) // reach the screen's own check
  await submit({ confirm: false })
  await page.waitForFunction(() => document.querySelector('.admin-accounts [role="alert"]')?.textContent.includes('Confirmá la operación'))
  assert.equal(await page.$$eval('.account-list tbody tr', rows => rows.filter(r => r.textContent.includes('Inactiva')).length), 0, 'sin confirmación no se desactiva')
  await submit()
  await notice('Cuenta desactivada'); await listed()
  await page.waitForFunction(email => [...document.querySelectorAll('.account-list tbody tr')].some(r => r.textContent.includes(email) && r.textContent.includes('Inactiva')), {}, SECOND.email)
  checkpoint('desactivación: sin la confirmación explícita no avanza; con contraseña y confirmación se desactiva')

  // 5. Deactivated account: no actions (the API has no reactivation); the last admin stays blocked.
  const inactive = await page.$$eval('.account-list tbody tr', (rows, email) => { const r = rows.find(x => x.textContent.includes(email))
    return { buttons: r.querySelectorAll('button:not(:disabled)').length, text: r.textContent } }, SECOND.email)
  assert.equal(inactive.buttons, 0, 'una cuenta inactiva no ofrece acciones')
  assert.ok(!/Reactivar/i.test(inactive.text))
  assert.equal(await page.$eval(`button[aria-label="Desactivar ${ADMIN.email}"]`, b => b.disabled), true)
  assert.equal((await deactivateViaApi(self.current_user_id, ADMIN.password)).status, 409)
  if (!before) assert.match(inactive.text, /Sin acciones/)
  await desktopAudit('desactivada'); await shoot('desactivada'); await mobileChecks('desactivada')
  checkpoint('cuenta desactivada sin acciones (no hay reactivación en la API); el último administrador sigue bloqueado (pantalla y 409)')

  // 6. Keyboard: Tab reaches the first action with a visible focus ring.
  if (!before) {
    assert.ok(await tabReaches(page, `button[aria-label="Rotar contraseña de ${ADMIN.email}"]`, 120), 'Tab llega a «Rotar contraseña»')
    const ring = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) } })
    assert.ok(ring.style !== 'none' && ring.width >= 2, `foco visible: ${JSON.stringify(ring)}`)
    await page.evaluate(() => document.activeElement?.blur())
    checkpoint('teclado: Tab alcanza las acciones con foco visible')
  }

  // 7. API error: the list fails (503) → alert and «Reintentar carga», no invented accounts.
  await page.setRequestInterception(true); page.on('request', onIntercepted); failList = true
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.admin-accounts [role="alert"]')
  assert.match(await page.$eval('.admin-accounts [role="alert"]', e => e.textContent), /API ficticia temporalmente no disponible/)
  assert.equal(await page.$('.account-list tbody tr'), null)
  await desktopAudit('error de API'); await shoot('error-api'); await mobileChecks('error de API')
  failList = false; page.off('request', onIntercepted); await page.setRequestInterception(false)
  await clickText('Reintentar carga'); await listed()
  checkpoint('error de la API: aviso con el detalle, «Reintentar carga» y recuperación; sin cuentas inventadas')

  assert.deepEqual(errors, [])
  assert.deepEqual([...new Set(external)], [])
  const receipt = { status: 'passed', label, mode: before ? 'before (captures only)' : 'full', source: 'generated_fictional_only', sqlite: true, postgis: false, checks, browser_errors: errors }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify(receipt, null, 2))
} finally {
  await browser?.close()
  fixture.stdin.end('stop\n')
  const stopped = await Promise.race([closed.then(() => true), delay(5000).then(() => false)])
  if (!stopped) fixture.kill()
  await vite?.stop().catch(error => { console.error('Owned Vite cleanup:', error.message) })
}
