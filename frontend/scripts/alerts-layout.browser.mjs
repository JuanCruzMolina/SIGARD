// Administración v2 · Alertas internas (F6.2): visual states of the redesigned screen.
// Owns its environment like test:alerts:browser: Vite (5173) + the local administrative API (8767)
// in session mode (disposable SQLite, generated admin, generated fictional alerts source).
// Rules and evaluations are created through the API; decisions through the screen. Only the
// «API error» state is intercepted (GET /alerts/candidates answers 500).
//   states: without candidates, with candidates, API error, approved and discarded decisions;
//   desktop 1440 and mobile 390; AA contrast, keyboard, 44 px targets, texts ≥ 14 px on mobile.
// Screenshots (private): data/interim/official/ux-admin-v2-f6-2/<label>/alertas-<state>-<desktop|mobile>.private.png
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { auditAccessibility, tabReaches } from './browser-a11y.mjs'
import { alertsRuntime, ALERTS_API } from './dev-alerts.mjs'
import { portAvailable, startDevelopment } from './dev.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const argument = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined
const label = runLabel(argument('--label'))
const frontendRoot = fileURLToPath(new URL('..', import.meta.url))
const outputBase = resolve(frontendRoot, '..', 'data/interim/official/ux-admin-v2-f6-2')
const origin = 'http://127.0.0.1:5173'
for (const port of [5173, 8767]) assert.ok(await portAvailable(port), `Port ${port} must be free; no existing service will be stopped`)

// Independent epidemiological week (Sunday–Saturday, week 1 holds 4 January).
function epiWeek(iso) {
  const [y, m, d] = iso.split('-').map(Number), day = Date.UTC(y, m - 1, d)
  for (let year = y + 1; year >= y - 1; year--) {
    const jan4 = new Date(Date.UTC(year, 0, 4)), start = jan4.getTime() - jan4.getUTCDay() * 86400000
    if (start <= day) return { year, week: Math.floor((day - start) / 604800000) + 1 }
  }
}

let failCandidates = false
const runtime = alertsRuntime({ mode: 'session', source: 'fictional' }); runtime.announce = () => {}
let environment = await startDevelopment(runtime)
const browser = await puppeteer.launch({ headless: true })
const errors = [], external = [], checks = []
const checkpoint = name => { checks.push(name); console.log(`✔ ${name}`) }
try {
  const output = await newRunDirectory(outputBase, label)
  const { email, password } = runtime.service.credentials
  const page = await browser.newPage(); page.setDefaultTimeout(30000)
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()) })
  await page.setRequestInterception(true)
  page.on('request', r => {
    const u = new URL(r.url())
    if (!['http:', 'https:'].includes(u.protocol)) return r.continue()
    if (u.protocol === 'https:' && ['fonts.googleapis.com', 'fonts.gstatic.com'].includes(u.hostname)) return r.continue()
    if (u.hostname !== '127.0.0.1' || !['5173', '8767'].includes(u.port)) { external.push(u.origin); return r.abort() }
    if (failCandidates && u.pathname === '/api/v1/admin/alerts/candidates' && r.method() === 'GET')
      return r.respond({ status: 500, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': origin }, body: '{"detail":"Fallo ficticio de la prueba"}' })
    return r.continue()
  })
  const settle = (ms = 400) => new Promise(done => setTimeout(done, ms))
  const noHorizontalScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)
  const shoot = async (name, widths = [['desktop', 1440], ['mobile', 390]]) => {
    for (const [kind, width] of widths) {
      await page.setViewport({ width, height: 1000 }); await settle()
      assert.ok(await noHorizontalScroll(), `${name} ${kind}: sin scroll horizontal`)
      await page.screenshot({ path: resolve(output, `alertas-${name}-${kind}.private.png`), fullPage: true })
    }
    await page.setViewport({ width: 1440, height: 1000 })
  }
  const clickText = async (text, scope = 'main') => {
    await page.waitForFunction((text, scope) => [...document.querySelector(scope).querySelectorAll('button')].some(b => b.textContent.trim() === text && !b.disabled), {}, text, scope)
    await page.evaluate((text, scope) => [...document.querySelector(scope).querySelectorAll('button')].find(b => b.textContent.trim() === text && !b.disabled).click(), text, scope)
  }
  const tab = async id => { await page.click(`[data-tab="${id}"]`); await page.waitForSelector(`[data-tab="${id}"][aria-pressed="true"]`) }
  const loaded = () => page.waitForFunction(() => document.querySelectorAll('.alerts-evaluate option').length > 0)
  const openAlerts = async () => { await page.goto(`${origin}/admin/alertas`, { waitUntil: 'domcontentloaded' }); await page.waitForSelector('.alerts-banner'); await loaded() }
  const mobileChecks = async name => {
    await page.setViewport({ width: 390, height: 900 }); await settle()
    assert.ok(await noHorizontalScroll(), `${name}: sin scroll horizontal en 390 px`)
    const targets = await page.$$eval('main button, main a[href], main select, main textarea, main summary', e => e
      .filter(x => x.getClientRects().length && x.getBoundingClientRect().right > 0)
      .map(x => { const r = x.getBoundingClientRect(); return [x.textContent.trim().slice(0, 30) || x.tagName, Math.round(r.width), Math.round(r.height)] })
      .filter(([, w, h]) => w < 44 || h < 44))
    assert.deepEqual(targets, [], `${name}: áreas táctiles de 44 px: ${JSON.stringify(targets)}`)
    const small = await page.evaluate(() => {
      const found = [], walker = document.createTreeWalker(document.querySelector('main'), NodeFilter.SHOW_TEXT)
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const e = node.parentElement
        if (!node.textContent.trim() || !e.getClientRects().length || e.closest('svg, option')) continue
        const size = parseFloat(getComputedStyle(e).fontSize); if (size < 14) found.push(`${node.textContent.trim().slice(0, 30)} (${size} px, ${e.className || e.tagName})`)
      }
      return [...new Set(found)]
    })
    assert.deepEqual(small, [], `${name}: textos ≥ 14 px: ${JSON.stringify(small)}`)
    const audit = await auditAccessibility(page, 'main')
    assert.deepEqual(audit.unnamed, [], `${name}: controles con nombre (390)`); assert.deepEqual(audit.lowContrast, [], `${name}: contraste AA (390)`)
    await page.setViewport({ width: 1440, height: 1000 })
  }
  await page.setViewport({ width: 1440, height: 1000 })

  // Login, then the API session for setup.
  await page.goto(`${origin}/admin/alertas`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.admin-login')
  await page.type('.admin-login input[type="email"]', email); await page.type('.admin-login input[type="password"]', password)
  await page.click('.admin-login button'); await page.waitForSelector('.alerts-banner'); await loaded()
  const token = await page.evaluate(() => sessionStorage.getItem('sigard_admin_token'))
  const api = (path, options = {}) => fetch(`${ALERTS_API}/api/v1/admin/alerts${path}`, { ...options, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
    .then(async response => { assert.ok(response.ok, `${path}: ${response.status}`); return response.json() })

  // 1. Without candidates (and without rules): structure of the screen.
  assert.deepEqual(await page.$$eval('.ui-breadcrumb a', a => a.map(x => [x.textContent, x.getAttribute('href')])), [['Inicio', '/admin/inicio']])
  assert.equal(await page.$eval('.admin-header h1', e => e.textContent), 'Alertas internas')
  assert.deepEqual(await page.$$eval('.alerts-steps li', l => l.map(x => x.textContent.trim())),
    ['1 Regla', '2 Evaluación semanal', '3 Alerta candidata', '4 Revisión humana', '5 Aviso interno aprobado'])
  assert.match(await page.$eval('.alerts-banner', e => e.textContent), /Ningún algoritmo publica alertas\..*publicación ciudadana está bloqueada/s)
  assert.equal(await page.$eval('[data-tab="pending"]', e => getComputedStyle(e).borderBottomColor), 'rgb(8, 123, 117)', 'pestaña activa subrayada')
  assert.match(await page.$eval('.alerts-list', e => e.textContent), /No hay alertas candidatas pendientes de revisión/)
  assert.match(await page.$eval('.alerts-active', e => e.textContent), /No hay reglas activas/)
  assert.ok(await page.$('.alerts-side .alerts-evaluate select'), 'la evaluación está en la columna lateral')
  await shoot('sin-candidatas')
  await mobileChecks('sin candidatas')
  checkpoint('sin candidatas: ruta, franja de 5 pasos, pestañas, tarjeta vacía y columna con evaluación y reglas activas')

  // 2. With candidates: two rules and one evaluation through the API (fictional source).
  const status = await api('/status')
  const quantityModel = status.models.find(m => m.capability === 'quantity').id
  await api('/rules', { method: 'POST', body: JSON.stringify({ name: 'Regla ficticia de pantalla', capability: 'quantity', model: quantityModel, radio_ids: ['FX0000001', 'FX0000002'], threshold: 5, consecutive_weeks: 1, enabled: true }) })
  let created = 0
  for (const week of status.weeks.slice(-8)) {
    created += (await api('/evaluations', { method: 'POST', body: JSON.stringify({ target_week: week.target_week }) })).evaluation.summary.created ?? 0
    if ((await api('/candidates?status=pending')).length >= 2) break
  }
  const pending = await api('/candidates?status=pending')
  assert.ok(pending.length >= 2, `al menos dos candidatas pendientes (${pending.length})`)
  await openAlerts()
  await page.waitForFunction(n => document.querySelectorAll('[data-status="pending"]').length === n, {}, pending.length)
  const firstId = Number(await page.$eval('[data-status="pending"]', e => e.dataset.candidate))
  const first = pending.find(c => c.id === firstId)
  const card = `[data-candidate="${first.id}"]`
  const view = await page.$eval(card, e => ({
    title: e.querySelector('h3').textContent, badge: e.querySelector('.ui-badge').textContent, icon: Boolean(e.querySelector('.ui-badge svg')),
    facts: [...e.querySelectorAll('.alerts-facts dt')].map(d => d.textContent), week: e.querySelector('.alerts-facts .mono-week')?.textContent,
    link: e.querySelector('.alerts-map-link')?.getAttribute('href'), font: getComputedStyle(e.querySelector('h3 .mono')).fontFamily }))
  const se = epiWeek(first.target_week)
  assert.equal(view.title, `Radio ${first.radio_id} · semana del ${first.target_week.split('-').reverse().join('/')}`)
  assert.equal(view.badge, 'Pendiente de revisión'); assert.ok(view.icon, 'insignia con ícono')
  assert.deepEqual(view.facts, ['Regla', 'Condición', 'Pregunta y modelo', 'Semana epidemiológica'])
  assert.equal(view.week, `SE ${se.week}/${se.year}`, 'SE calculada aparte')
  assert.ok(view.font.includes('IBM Plex Mono'))
  const link = new URL(view.link, origin)
  assert.equal(link.pathname, '/admin/predictivo')
  assert.deepEqual([link.searchParams.get('anio'), link.searchParams.get('se'), link.searchParams.get('vista')], [String(se.year), String(se.week), 'cuantos'])
  assert.equal(link.searchParams.get('radio'), null, 'un radio ficticio no se pasa al visor (sólo códigos de 9 dígitos)')
  assert.match(await page.$eval('.alerts-active', e => e.textContent), /Regla ficticia de pantalla/)
  assert.match(await page.$eval('[data-tab="pending"]', e => e.textContent), new RegExp(`Pendientes \\(${pending.length}\\)`))
  const desktopAudit = await auditAccessibility(page, 'main')
  assert.deepEqual(desktopAudit.unnamed, []); assert.deepEqual(desktopAudit.lowContrast, [], 'contraste AA (1440)')
  // Keyboard: Tab reaches «Aprobar como aviso interno» with a visible focus ring.
  assert.ok(await tabReaches(page, `${card} .alerts-actions .primary-button`, 120), 'Tab llega a «Aprobar»')
  const ring = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) } })
  assert.ok(ring.style !== 'none' && ring.width >= 2, `foco visible: ${JSON.stringify(ring)}`)
  await page.evaluate(() => document.activeElement?.blur())
  await shoot('con-candidatas')
  await mobileChecks('con candidatas')
  checkpoint(`con candidatas (${pending.length}): título, insignia con ícono, ficha (regla, condición, modelo, SE ${se.week}/${se.year}), evidencia, «Ver en el mapa», AA y teclado`)

  // 3. Decisions through the screen: approve the first, discard the second.
  const decide = async (id, action, comment) => {
    const scope = `[data-candidate="${id}"]`
    await clickText(action === 'approve' ? 'Aprobar como aviso interno' : 'Descartar', scope)
    await page.waitForSelector(`${scope} textarea`); await page.type(`${scope} textarea`, comment)
    await clickText(action === 'approve' ? 'Confirmar aprobación' : 'Confirmar descarte', scope)
    await page.waitForFunction(id => !document.querySelector(`[data-candidate="${id}"][data-status="pending"]`), {}, id)
  }
  const second = pending.find(c => c.id !== first.id)
  // F6.3: the side-menu counter follows each decision without leaving the section (no badge at 0).
  const navBadge = () => page.$eval('a.admin-nav-item[href="/admin/alertas"]', a => a.querySelector('.admin-nav-badge')?.textContent ?? '')
  const badgeIs = expected => page.waitForFunction(expected => (document.querySelector('a.admin-nav-item[href="/admin/alertas"] .admin-nav-badge')?.textContent ?? '') === expected, { timeout: 5000 }, expected)
  const shown = n => n > 0 ? String(n) : ''
  assert.equal(await navBadge(), String(pending.length), 'contador del menú = candidatas pendientes')
  const pageUrl = page.url()
  await decide(first.id, 'approve', 'Aprobada en la prueba de pantalla (ficticio)')
  await badgeIs(shown(pending.length - 1))
  await decide(second.id, 'discard', 'Descartada en la prueba de pantalla (ficticio)')
  await badgeIs(shown(pending.length - 2))
  assert.equal(page.url(), pageUrl, 'sin cambiar de sección')
  checkpoint(`contador del menú: ${pending.length} → ${pending.length - 1} → ${pending.length - 2} al decidir, sin cambiar de sección`)
  await tab('history')
  await page.waitForSelector(`[data-candidate="${first.id}"][data-status="approved_internal"]`)
  const decided = await page.$$eval('[data-status="approved_internal"], [data-status="discarded"]', cards => Object.fromEntries(cards.map(c => [c.dataset.status,
    { badge: c.querySelector('.ui-badge').textContent, tone: [...c.querySelector('.ui-badge').classList].find(k => k.startsWith('ui-tone-')), color: getComputedStyle(c.querySelector('.ui-badge')).color, text: c.querySelector('.alerts-decided').textContent }])))
  assert.deepEqual([decided.approved_internal.badge, decided.approved_internal.tone], ['Aviso interno aprobado', 'ui-tone-ok'])
  assert.deepEqual([decided.discarded.badge, decided.discarded.tone], ['Descartada', 'ui-tone-alert'])
  assert.match(decided.approved_internal.text, /Aprobada en la prueba de pantalla/)
  assert.match(decided.discarded.text, /^Motivo: Probable falsa alarma · «Descartada en la prueba de pantalla/)
  assert.equal(await page.$(`[data-candidate="${first.id}"] .alerts-actions`), null, 'una candidata decidida no tiene botones de decisión')
  const actions = await page.$$eval('.alerts-audit li', l => l.map(x => x.dataset.action))
  for (const action of ['candidate_approved', 'candidate_discarded']) assert.ok(actions.includes(action), action)
  await shoot('decisiones')
  await mobileChecks('historial')
  checkpoint('decisión aprobada (insignia verde) y descartada (insignia de alerta, motivo) en el historial y la auditoría')

  // 4. Rules tab and form inside a card.
  await tab('rules')
  assert.equal(await page.$$eval('[data-rule].ui-card', l => l.length), 1)
  await clickText('Nueva regla', '.admin-header')
  await page.waitForSelector('.alerts-form-card .alerts-rule-form')
  assert.equal(await page.$eval('[data-tab="rules"]', e => e.getAttribute('aria-pressed')), 'true', '«Nueva regla» del encabezado abre el formulario en Reglas')
  await shoot('regla-nueva')
  await mobileChecks('formulario de regla')
  await clickText('Cancelar', '.alerts-rule-form')
  checkpoint('reglas en tarjetas y «Nueva regla» del encabezado abre el formulario')

  // 5. API error: the candidates request fails → an alert, no invented content.
  failCandidates = true
  await page.goto(`${origin}/admin/alertas`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.admin-alerts .form-error[role="alert"]')
  assert.match(await page.$eval('.admin-alerts .form-error[role="alert"]', e => e.textContent), /Fallo ficticio de la prueba/)
  assert.equal(await page.$('[data-status="pending"]'), null)
  await shoot('error-api')
  await mobileChecks('error de API')
  failCandidates = false
  checkpoint('error de la API: aviso con el detalle y sin candidatas inventadas')

  assert.deepEqual(errors, []); assert.deepEqual([...new Set(external)], [])
  const receipt = { status: 'passed', label, source: 'generated_fictional_only', checks, browser_errors: errors }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify(receipt, null, 2))
} finally {
  await browser.close()
  if (environment) { await environment.stop(); await environment.closed; environment = undefined }
}
