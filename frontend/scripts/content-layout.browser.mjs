// Administración v2 · Contenido preventivo (F6.4): visual states of the redesigned screen.
// Owns its environment like test:prevention:browser: Vite (5173) + the demo API (8766, disposable
// SQLite seeded with the 5 published sections, session-only admin). Fictitious text only.
//   states: section list, editing, draft with unpublished changes, new section published (and the
//   same text on the public page), API error; desktop 1440 and mobile 390; AA contrast, keyboard,
//   44 px targets, texts ≥ 14 px on mobile, the section tabs scroll sideways on mobile.
// No DevTools request interception except during the «API error» state (a GET only): while it is
// on, Chromium sometimes cancels a CORS-preflighted POST (see docs/diseno/admin-v2/inventario.md).
// --before: captures only (selectors shared with the previous design), no layout assertions.
// Screenshots (private): data/interim/official/ux-admin-v2-f6-4/<label>/contenido-<state>-<desktop|mobile>.private.png
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { auditAccessibility, tabReaches } from './browser-a11y.mjs'
import { demoRuntime } from './dev-demo.mjs'
import { portAvailable, startDevelopment } from './dev.mjs'
import { newRunDirectory, runLabel } from './private-output.mjs'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const argument = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined
const before = process.argv.includes('--before')
const label = runLabel(argument('--label'))
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const outputBase = resolve(root, 'data/interim/official/ux-admin-v2-f6-4')
const origin = 'http://127.0.0.1:5173', api = 'http://127.0.0.1:8766'
for (const port of [5173, 5174, 8766]) assert.ok(await portAvailable(port), `Port ${port} must be free; no existing service will be stopped`)

const NEW = { slug: 'prueba-pantalla-contenido', title: 'Sección ficticia de la prueba de pantalla',
  body: 'Texto ficticio para comprobar la vista previa.\n\n- Primer paso ficticio\n- Segundo paso **ficticio**',
  source_label: 'Fuente ficticia de la prueba', source_url: 'https://example.org/fuente-ficticia' }
const MARKER = 'Paso ficticio agregado por la prueba de pantalla.'

let session, service, browser
const errors = [], external = [], checks = []
const checkpoint = text => { const name = before ? `captura (sin aserciones de diseño): ${text}` : text; checks.push(name); console.log(`✔ ${name}`) }
try {
  const runtime = demoRuntime()
  const original = runtime.startCompanion
  runtime.startCompanion = () => { service = original(); return service }
  runtime.announce = () => {}
  session = await startDevelopment(runtime)
  const output = await newRunDirectory(outputBase, label)
  browser = await puppeteer.launch({ headless: true, args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'] })
  const page = await browser.newPage(); page.setDefaultTimeout(20000)
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()) })
  page.on('request', r => { const u = new URL(r.url()); if (/^https?:$/.test(u.protocol) && u.hostname !== '127.0.0.1') external.push(u.origin) })
  let failList = false
  const onIntercepted = r => {
    const u = new URL(r.url())
    if (failList && r.method() === 'GET' && u.port === '8766' && u.pathname === '/api/v1/admin/prevention')
      return r.respond({ status: 500, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': origin }, body: '{"detail":"Fallo ficticio del listado de contenido."}' })
    return r.continue()
  }

  const settle = (ms = 400) => delay(ms)
  const noHorizontalScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)
  const shoot = async (name, widths = [['desktop', 1440], ['mobile', 390]]) => {
    for (const [kind, width] of widths) {
      await page.setViewport({ width, height: 1000 }); await settle()
      assert.ok(await noHorizontalScroll(), `${name} ${kind}: sin scroll horizontal`)
      await page.screenshot({ path: resolve(output, `contenido-${name}-${kind}.private.png`), fullPage: true })
    }
    await page.setViewport({ width: 1440, height: 1000 }); await settle(200)
  }
  const clickText = async (text, scope = 'main') => {
    await page.waitForFunction((text, scope) => [...document.querySelector(scope).querySelectorAll('button')].some(b => b.textContent.trim() === text && !b.disabled), {}, text, scope)
    await page.evaluate((text, scope) => [...document.querySelector(scope).querySelectorAll('button')].find(b => b.textContent.trim() === text && !b.disabled).click(), text, scope)
  }
  const fill = async (selector, value) => {
    await page.$eval(selector, (e, v) => { const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(e, v); e.dispatchEvent(new Event('input', { bubbles: true })) }, value)
  }
  const notice = text => page.waitForFunction(text => document.querySelector('.admin-prevention .account-notice')?.textContent.includes(text), {}, text)
  const openSection = async title => {
    await page.evaluate(title => [...document.querySelectorAll('.prevention-section-list li button')].find(b => b.textContent.includes(title)).click(), title)
    await page.waitForSelector('.prevention-preview article')
  }
  const mobileChecks = async name => {
    if (before) return
    await page.setViewport({ width: 390, height: 900 }); await settle()
    assert.ok(await noHorizontalScroll(), `${name}: sin scroll horizontal en 390 px`)
    const targets = await page.$$eval('main button, main a[href], main select, main textarea, main input', e => e
      .filter(x => x.checkVisibility() && x.getBoundingClientRect().width > 0)
      .map(x => { const r = x.getBoundingClientRect(); return [x.textContent.trim().slice(0, 30) || x.name || x.tagName, Math.round(r.width), Math.round(r.height)] })
      .filter(([, w, h]) => w < 44 || h < 44))
    assert.deepEqual(targets, [], `${name}: áreas táctiles de 44 px: ${JSON.stringify(targets)}`)
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
    // Section tabs: one row that scrolls sideways (never wraps to a second line).
    const tabs = await page.$eval('.prevention-section-list ul', ul => ({ rows: new Set([...ul.children].map(li => Math.round(li.getBoundingClientRect().top))).size,
      scrolls: ul.scrollWidth > ul.clientWidth, overflow: getComputedStyle(ul).overflowX }))
    assert.ok(tabs.rows === 1 && tabs.scrolls && ['auto', 'scroll'].includes(tabs.overflow), `${name}: pestañas de secciones en una fila con desplazamiento: ${JSON.stringify(tabs)}`)
    const audit = await auditAccessibility(page, 'main')
    assert.deepEqual(audit.unnamed, [], `${name}: controles con nombre (390)`); assert.deepEqual(audit.lowContrast, [], `${name}: contraste AA (390)`)
    await page.setViewport({ width: 1440, height: 1000 }); await settle(200)
  }
  const desktopAudit = async name => {
    if (before) return
    const audit = await auditAccessibility(page, 'main')
    assert.deepEqual(audit.unnamed, [], `${name}: controles con nombre (1440)`); assert.deepEqual(audit.lowContrast, [], `${name}: contraste AA (1440)`)
  }
  await page.setViewport({ width: 1440, height: 1000 })

  // 1. Section list (nothing selected yet).
  await page.goto(`${origin}/admin/contenido`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.admin-login')
  await page.type('.admin-login input[type="email"]', service.credentials.email)
  await page.type('.admin-login input[type="password"]', service.credentials.password)
  await page.click('.admin-login button')
  await page.waitForFunction(() => document.querySelectorAll('.prevention-section-list li button').length === 5)
  const sections = await (await fetch(`${api}/api/v1/admin/prevention`, { headers: { Authorization: `Bearer ${await page.evaluate(() => sessionStorage.getItem('sigard_admin_token'))}` } })).json()
  if (!before) {
    assert.deepEqual(await page.$$eval('.ui-breadcrumb a', a => a.map(x => [x.textContent, x.getAttribute('href')])), [['Inicio', '/admin/inicio']])
    assert.equal(await page.$eval('.admin-header h1', e => e.textContent), 'Contenido preventivo')
    assert.ok(await page.$('.admin-header .ui-button-primary'), '«Nueva sección» en el encabezado')
    const items = await page.$$eval('.prevention-section-list li button', b => b.map(x => ({ title: x.querySelector('strong').textContent, badge: x.querySelector('.ui-badge')?.textContent, icon: Boolean(x.querySelector('.ui-badge svg')) })))
    assert.deepEqual(items.map(i => i.title), sections.map(s => s.title), 'lista = secciones de la API, en su orden')
    assert.ok(items.every(i => i.icon && /^Publicada · v\d+$/.test(i.badge)), `insignias con ícono y estado real: ${JSON.stringify(items.map(i => i.badge))}`)
    for (const selector of ['.prevention-section-list', '.prevention-empty']) assert.equal(await page.$eval(selector, e => getComputedStyle(e).borderTopLeftRadius), '14px', `${selector} como tarjeta`)
  }
  await desktopAudit('lista'); await shoot('lista'); await mobileChecks('lista')
  checkpoint(`lista de ${sections.length} secciones con su estado real y «Nueva sección» en el encabezado`)

  // 2. Editing a published section: state, form, public preview and history.
  const first = sections[0]
  await openSection(first.title)
  await page.waitForFunction(() => document.querySelector('.prevention-history li')?.textContent.includes('Carga inicial'))
  if (!before) {
    assert.match(await page.$eval('.prevention-editor .prevention-state', e => e.textContent), new RegExp(`Publicada · v${first.version}`))
    assert.equal(await page.$eval('.prevention-preview h3', e => e.textContent), 'Vista previa del borrador')
    assert.ok(await tabReaches(page, '.prevention-form input[name="title"]', 160), 'Tab llega al título')
    const ring = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) } })
    assert.ok(ring.style !== 'none' && ring.width >= 2, `foco visible: ${JSON.stringify(ring)}`)
    await page.evaluate(() => document.activeElement?.blur())
    assert.ok(await page.$('.prevention-history.ui-card'), 'historial en su propia tarjeta')
  }
  await desktopAudit('edición'); await shoot('edicion'); await mobileChecks('edición')
  checkpoint('edición: estado, formulario, vista previa pública e historial; teclado con foco visible')

  // 3. Draft with unpublished changes: the public API keeps the published text.
  await page.$eval('.prevention-form textarea[name="body"]', (e, marker) => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(e, `${e.value}\n- ${marker}`); e.dispatchEvent(new Event('input', { bubbles: true }))
  }, MARKER)
  await page.waitForFunction(marker => document.querySelector('.prevention-preview')?.textContent.includes(marker), {}, MARKER)
  await clickText('Guardar borrador'); await notice('Borrador guardado')
  assert.match(await page.$eval('.prevention-editor', e => e.textContent), /cambios sin publicar/)
  assert.ok(!(await (await fetch(`${api}/api/v1/public/prevention`)).text()).includes(MARKER), 'el borrador no es público')
  if (!before) {
    const badge = await page.$eval('.prevention-editor .prevention-state .ui-badge', e => ({ text: e.textContent, tone: [...e.classList].find(c => c.startsWith('ui-tone-')) }))
    assert.deepEqual(badge, { text: 'Publicada · cambios sin publicar', tone: 'ui-tone-alert' })
    assert.ok(await page.$eval('.prevention-section-list li button[aria-pressed="true"] .ui-badge', e => e.textContent === 'Publicada · cambios sin publicar'))
  }
  await desktopAudit('borrador'); await shoot('borrador'); await mobileChecks('borrador')
  checkpoint('borrador con cambios sin publicar: insignia en el editor y en la lista; la página pública no cambia')

  // 4. New section: draft, confirmation and publication; the public page shows the same text.
  await clickText('Nueva sección', before ? 'main' : '.admin-header')
  await page.waitForSelector('.prevention-form input[name="slug"]')
  for (const [field, value] of Object.entries(NEW)) await fill(`.prevention-form [name="${field}"]`, value)
  await clickText('Guardar borrador'); await notice('Borrador guardado')
  await page.waitForFunction(title => document.querySelector('.prevention-section-list li button[aria-pressed="true"]')?.textContent.includes(title), {}, NEW.title)
  const preview = await page.$eval('.prevention-preview article', a => ({ title: a.querySelector('h4').textContent, body: [...a.children].slice(1, -1).map(n => n.innerText.trim()).join('\n'), source: a.querySelector('.section-source')?.innerText }))
  await clickText('Publicar'); await page.waitForSelector('.prevention-confirm[role="alertdialog"]')
  assert.match(await page.$eval('.prevention-confirm h3', e => e.textContent), /versión 1/)
  await desktopAudit('confirmación'); await shoot('confirmacion', [['desktop', 1440]])
  await clickText('Confirmar publicación'); await notice('Versión 1 publicada')
  await page.waitForFunction(() => document.querySelector('.prevention-history li strong')?.textContent === 'Publicada')
  await desktopAudit('publicada'); await shoot('publicada'); await mobileChecks('publicada')
  const publicPage = await browser.newPage()
  await publicPage.setViewport({ width: 1440, height: 1000 })
  await publicPage.goto(`${origin}/prevencion`, { waitUntil: 'domcontentloaded' })
  const article = `.extra-section-list article[data-slug="${NEW.slug}"]`
  await publicPage.waitForSelector(article)
  const published = await publicPage.$eval(article, a => ({ title: a.querySelector('h3').textContent, body: [...a.children].slice(1, -1).map(n => n.innerText.trim()).join('\n'), source: a.querySelector('.section-source')?.innerText }))
  assert.equal(published.title, preview.title, 'mismo título en la vista previa y en el sitio público')
  assert.equal(published.body, preview.body, 'mismo texto en la vista previa y en el sitio público')
  assert.equal(published.source, `${preview.source} · versión 1`, 'misma fuente (el sitio público agrega la versión)')
  await publicPage.$eval(article, e => e.scrollIntoView())
  await publicPage.screenshot({ path: resolve(output, 'contenido-sitio-publico-desktop.private.png') })
  await publicPage.close()
  checkpoint('nueva sección: borrador, confirmación «versión 1», publicada; el sitio público muestra el mismo título, texto y fuente que la vista previa')

  // 5. API error: the section list fails (500) → an alert, no invented sections.
  await page.setRequestInterception(true); page.on('request', onIntercepted); failList = true
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.admin-prevention .admin-error')
  assert.match(await page.$eval('.admin-prevention .admin-error', e => e.textContent), /Fallo ficticio del listado de contenido/)
  assert.equal(await page.$('.prevention-section-list li button'), null)
  await desktopAudit('error de API'); await shoot('error-api')
  failList = false; page.off('request', onIntercepted); await page.setRequestInterception(false)
  checkpoint('error de la API: aviso con el detalle y sin secciones inventadas')

  assert.deepEqual(errors, [])
  assert.deepEqual([...new Set(external)], [], 'nada sale de 127.0.0.1 (las fuentes son locales desde F7a)')
  const receipt = { status: 'passed', label, mode: before ? 'before (captures only)' : 'full', source: 'generated_fictional_only', sqlite: true, postgis: false, checks, browser_errors: errors }
  await writeFile(resolve(output, 'receipt.private.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify(receipt, null, 2))
} finally {
  await browser?.close()
  if (session) { await session.stop(); await session.closed }
}
