// Uses an existing Puppeteer installation, not a new product dependency.
// Run Vite with the normal dev command first. This script owns only its fixture API.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const puppeteer = require(process.env.SIGARD_BROWSER_MODULE || 'puppeteer')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const output = resolve(root, 'frontend/.tmp')
const integral = process.env.SIGARD_INTEGRAL_REVIEW === '1'
const postgis = process.env.SIGARD_POSTGIS_BROWSER === '1'
const frontendOrigin = process.env.SIGARD_BROWSER_FRONTEND_URL || 'http://127.0.0.1:5173'
assert.ok(['http://127.0.0.1:5173', 'http://127.0.0.1:5174'].includes(frontendOrigin))
const stage = postgis ? '17' : integral ? '15' : '14'
const fixture = spawn(resolve(root, 'backend/.venv/Scripts/python.exe'), ['-B', 'backend/tests/browser_admin_fixture.py', ...(integral ? ['--integral'] : [])], {cwd:root, stdio:['pipe','pipe','pipe'], windowsHide:true})
const report = { checks: [], pageErrors: [], reactErrors: [], viewports: [1440,390], database: 'disposable SQLite', postgresql_verified: false }
if(integral) Object.assign(report,{stage:15,defects:[],accessibility:[]})
let browser
let fixtureErrors = ''
fixture.stderr.on('data', data => { fixtureErrors += data.toString() })
const closed = new Promise(resolve => fixture.once('exit', resolve))
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))

try {
  const ready = await new Promise((resolve, reject) => {
    let stdout = ''
    const timeout = setTimeout(() => reject(new Error('No inició la API ficticia')), 15000)
    fixture.on('error', e => {clearTimeout(timeout);reject(e)})
    fixture.stdout.on('data', data => {
      stdout += data.toString()
      if (stdout.includes('\n')) {clearTimeout(timeout);resolve(JSON.parse(stdout.split('\n')[0]))}
    })
    fixture.once('exit', () => {clearTimeout(timeout);reject(new Error('Terminó la API ficticia antes de iniciar'))})
  })
  assert.equal(ready.fixture,'sigard-disposable-admin')
  assert.equal(ready.postgis, postgis)
  if(postgis) Object.assign(report,{database:'disposable PostgreSQL/PostGIS',postgresql_verified:true})
  const api = `http://127.0.0.1:${ready.port}`
  for (let i=0;i<50;i++) {
    try {if ((await fetch(api+'/health')).ok) break} catch { /* fixture starting */ }
    await delay(100)
  }
  browser = await puppeteer.launch({headless:true})
  const page = await browser.newPage()
  page.setDefaultTimeout(15000)
  await page.setViewport({width:1440,height:1000})
  page.on('pageerror', e=>{report.pageErrors.push(e.message);if(integral) (report.pageErrorStacks??=[]).push(e.stack)})
  page.on('console', m=>{if(m.type()==='error' && /React|hydration|unique.*key/i.test(m.text())) report.reactErrors.push(m.text())})
  let failListing = false
  let rejectReportOperation = null
  await page.setRequestInterception(true)
  page.on('request', request => {
    const url=new URL(request.url())
    if (url.pathname.startsWith('/api/v1/') && url.port==='8000') {
      if(rejectReportOperation && (rejectReportOperation==='export' ? url.pathname.endsWith('/citizen-reports/export.csv') && request.method()==='GET' : /^\/api\/v1\/admin\/citizen-reports\/[^/]+$/.test(url.pathname) && request.method()===(rejectReportOperation==='save'?'PATCH':'GET'))) {
        return request.respond({status:rejectReportOperation==='export'?403:401,contentType:'application/json',headers:{'access-control-allow-origin':'http://127.0.0.1:5173'},body:JSON.stringify({detail:'Sesión ficticia revocada.'})})
      }
      if (failListing && url.pathname==='/api/v1/admin/users' && request.method()==='GET') {
        return request.respond({status:503,contentType:'application/json',headers:{'access-control-allow-origin':frontendOrigin},body:JSON.stringify({detail:'API ficticia temporalmente no disponible.'})})
      }
      return request.continue({url:api+url.pathname+url.search})
    }
    if(postgis && !['127.0.0.1','localhost'].includes(url.hostname) && url.protocol.startsWith('http')) return request.abort()
    return request.continue()
  })
  const check = async (name, run) => {await run();report.checks.push(name)}
  const click = text => page.evaluate(text=>[...document.querySelectorAll('button')].find(b=>b.textContent===text).click(),text)
  const fill = async (selector,value) => {await page.click(selector);await page.keyboard.down('Control');await page.keyboard.press('KeyA');await page.keyboard.up('Control');await page.keyboard.press('Backspace');if(value) await page.type(selector,value)}
  const accountLoaded = () => page.waitForFunction(()=>document.querySelector('.account-list')?.getAttribute('aria-busy')==='false')
  const login = async (email,password,success=true) => {
    await page.waitForSelector('.admin-login')
    await fill('.admin-login input[type="email"]',email)
    await fill('.admin-login input[type="password"]',password)
    await click('Ingresar')
    await page.waitForSelector(success?'.admin-header':'.admin-login [role="alert"]')
  }
  const submitAction = async (password='fictitious-initial-password',next=null) => {
    if(next) {await fill('input[name="password"]',next);await fill('input[name="confirmation"]',next)}
    await fill('input[name="current_password"]',password)
    await page.click('input[name="confirmed"]')
    await page.click('.account-operation button[type="submit"]')
  }
  const defect = (id,details) => {if(!report.defects.some(item=>item.id===id)) report.defects.push({id,...details})}
  const accessibility = async context => {
    const cdp=await page.target().createCDPSession()
    const tree=await cdp.send('Accessibility.getFullAXTree')
    const unnamed=tree.nodes.filter(n=>!n.ignored && ['button','textbox','combobox','checkbox','radio','link'].includes(n.role?.value) && !n.name?.value?.trim()).map(n=>({role:n.role.value,node:n.backendDOMNodeId}))
    await cdp.detach()
    const contrast=await page.evaluate(()=>{
      const rgba=s=>(s.match(/[\d.]+/g)||[]).map(Number)
      const mix=(fg,bg)=>fg.slice(0,3).map((v,i)=>v*(fg[3]??1)+bg[i]*(1-(fg[3]??1)))
      const luminance=rgb=>rgb.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0)
      const ratio=(a,b)=>{const x=luminance(a),y=luminance(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05)}
      const result=[]
      for(const selector of ['.main-nav a','.public-radio-control small','.method-notice p','.risk-pill','.primary-button','.privacy-check span','.status-section form label','.admin-login label','.account-list tbody th']) {
        const e=document.querySelector(selector)
        if(!e || !e.getBoundingClientRect().width) continue
        let bg=[255,255,255]
        const ancestors=[]
        for(let p=e;p;p=p.parentElement) ancestors.unshift(p)
        for(const p of ancestors) bg=mix(rgba(getComputedStyle(p).backgroundColor),bg)
        const style=getComputedStyle(e),fg=mix(rgba(style.color),bg)
        const minimum=parseFloat(style.fontSize)>=24 || (parseFloat(style.fontSize)>=18.66 && parseInt(style.fontWeight)>=700)?3:4.5
        result.push({selector,ratio:Number(ratio(fg,bg).toFixed(2)),minimum})
      }
      const focus=document.querySelector('.public-radio-control select')
      if(focus && focus.matches(':focus-visible')) result.push({selector:'public-radio-focus',ratio:Number(ratio(rgba(getComputedStyle(focus).outlineColor),rgba(getComputedStyle(focus.parentElement).backgroundColor)[3]===1?rgba(getComputedStyle(focus.parentElement).backgroundColor):[251,252,248]).toFixed(2)),minimum:3})
      return result
    })
    report.accessibility.push({context,unnamed,contrast})
    if(unnamed.length) defect('unnamed-controls-'+context,{context,controls:unnamed})
    for(const item of contrast) if(item.ratio<item.minimum) defect('contrast-'+item.selector,{context,...item})
  }
  let trackingCode
  if(postgis) await check('formulario y seguimiento reales con PostgreSQL, geometría ficticia por API',async()=>{
    await page.goto(frontendOrigin+'/prevencion',{waitUntil:'networkidle0'})
    await page.focus('.report-map')
    await page.keyboard.press('ArrowRight');await page.keyboard.press('Enter')
    await page.waitForFunction(()=>document.querySelector('.coordinate-readout')?.textContent.includes('Punto seleccionado'))
    await page.click('.report-form input[value="agua_acumulada"]')
    await fill('.report-form textarea[name="description"]','Reporte completamente ficticio para comprobar persistencia, sin personas ni registros oficiales.')
    await page.click('.report-form input[name="privacy_accepted"]')
    await page.click('.submit-report')
    await page.waitForSelector('.report-confirmation output')
    trackingCode=await page.$eval('.report-confirmation output',e=>e.value||e.textContent)
    await page.click('.report-confirmation a')
    await page.click('.status-section button');await page.waitForSelector('.status-result')
    assert.match(await page.$eval('.status-result',e=>e.textContent),/Recibido/)
    const geometry=await page.evaluate(async()=>{
      const response=await fetch('http://localhost:8000/api/v1/public/territorial-context')
      return {status:response.status,body:await response.json()}
    })
    assert.equal(geometry.status,200)
    assert.equal(geometry.body.features[0].properties.radio_id,'fictional-radio')
    assert.equal(geometry.body.features[0].geometry.type,'Polygon')
  })
  if(integral) {
    await check('API pública temporal, selección por teclado y capas/semanas alineadas',async()=>{
      await page.goto('http://127.0.0.1:5173/mapa',{waitUntil:'networkidle0'})
      await click('MVP sintético y contexto')
      await page.waitForSelector('.public-radio-control select')
      assert.match(await page.$eval('.site-footer',e=>e.textContent),/API stage15-test-publication/)
      // A tooltip focus listener made Chromium tab through every polygon.
      // The map controls must lead directly to the existing textual selector.
      await page.focus('.map-layout .leaflet-container')
      let selectorReached = false
      for (let step=0;step<12;step++) {
        await page.keyboard.press('Tab')
        if (await page.evaluate(()=>document.activeElement?.matches('.public-radio-control select'))) { selectorReached=true;break }
        assert.equal(await page.evaluate(()=>document.activeElement?.matches('path.leaflet-interactive')),false)
      }
      assert.equal(selectorReached,true,'El selector público debe alcanzarse sin recorrer los polígonos')
      await page.focus('.public-radio-control select')
      await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');await page.keyboard.press('Escape')
      const radio=await page.$eval('.public-radio-control select',e=>e.value)
      assert.ok(radio)
      await page.waitForFunction(id=>document.querySelector('.radio-details h2')?.textContent===`Radio ${id}`,{},radio)
      await accessibility('public-radio-keyboard')
      await click('Contexto territorial')
      assert.match(await page.$eval('.radio-details',e=>e.textContent),/Densidad poblacional/)
      await click('Simulación espacial')
      const week=await page.$eval('#cutoff-week',e=>[...e.options].find(o=>o.value!==e.value).value)
      await page.select('#cutoff-week',week)
      assert.equal(await page.$eval('.public-radio-control select',e=>e.value),radio)
      assert.match(await page.$eval('.radio-details',e=>e.textContent),/No representa casos observados/)
      await mkdir(output,{recursive:true})
      for(const width of [1440,390]) {
        await page.setViewport({width,height:1000})
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
        await page.screenshot({path:resolve(output,`stage15-public-${width}.png`),fullPage:true})
      }
      await page.setViewport({width:1440,height:1000})
      for(const route of ['/dashboard','/validacion','/metodologia','/mapa']) {
        await page.click(`.main-nav a[href="${route}"]`)
        await page.waitForFunction(route=>location.pathname===route,{},route)
        await page.waitForSelector('.page-intro h1')
      }
    })
    await check('prevención, directorio, formulario y seguimiento ciudadano ficticio',async()=>{
      await page.goto('http://127.0.0.1:5173/prevencion',{waitUntil:'networkidle0'})
      await page.waitForSelector('#facilities-title')
      assert.equal(await page.$$eval('.facility-marker',n=>n.length),27)
      await fill('.search-control input','SIN RESULTADO FICTICIO')
      await page.waitForFunction(()=>document.querySelector('.facility-detail')?.textContent.includes('No hay resultados'))
      await fill('.search-control input','')
      await page.waitForFunction(()=>document.querySelectorAll('.facility-marker').length===27)
      await page.select('.facility-controls select','hospital')
      await page.waitForFunction(()=>document.querySelectorAll('.facility-marker').length===3)
      await page.select('.facility-controls select','caps')
      await page.waitForFunction(()=>document.querySelectorAll('.facility-marker').length===24)
      await page.select('.facility-controls select','all')
      await accessibility('prevention-desktop')
      await page.focus('.report-map')
      await page.keyboard.press('ArrowRight');await page.keyboard.press('Enter')
      const keyboardSelection=await page.$eval('.coordinate-readout',e=>e.textContent.includes('Punto seleccionado'))
      if(!keyboardSelection) {
        defect('report-location-keyboard',{context:'Enter no marca una ubicación en el mapa enfocado'})
        const rect=await page.$eval('.report-map',e=>{e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})
        await page.mouse.click(rect.x,rect.y)
      }
      await accessibility('report-location-selected')
      assert.ok(await page.$eval('.report-map-wrap',e=>getComputedStyle(e).outlineStyle!=='none'))
      await(await page.$('.report-form fieldset:nth-of-type(3)')).screenshot({path:resolve(output,'stage15-report-location.png')})
      await page.click('.report-form input[value="agua_acumulada"]')
      await fill('.report-form textarea[name="description"]','Reporte ficticio de prueba integral: recipientes vacíos en una plaza simulada, sin datos personales.')
      await page.click('.report-form input[name="privacy_accepted"]')
      await page.click('.submit-report')
      await page.waitForSelector('.report-confirmation output')
      trackingCode=await page.$eval('.report-confirmation output',e=>e.value||e.textContent)
      await page.click('.report-confirmation a')
      await page.waitForFunction(code=>document.querySelector('#tracking-code')?.value===code,{},trackingCode)
      await page.click('.status-section button')
      await page.waitForSelector('.status-result')
      assert.match(await page.$eval('.status-result',e=>e.textContent),/Recibido/)
      const publicStatus=await(await fetch(`${api}/api/v1/citizen-reports/status/${trackingCode}`)).json()
      assert.deepEqual(Object.keys(publicStatus).sort(),['tracking_code','status','created_at','updated_at','public_status_message'].sort())
      for(const width of [1440,390]) {
        await page.setViewport({width,height:1000})
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
        await accessibility('prevention-'+width)
        await(await page.$('.prevention-hero')).screenshot({path:resolve(output,`stage15-prevention-${width}.png`)})
      }
      await page.setViewport({width:1440,height:1000})
    })
  }
  if(!postgis) await check('público y A/B sin tokens, 263 radios, historial y métricas',async()=>{
    await page.goto('http://127.0.0.1:5173/mapa',{waitUntil:'networkidle0'})
    await click('MVP sintético y contexto')
    await page.waitForSelector('.public-radio-control select')
    assert.equal(await page.$$eval('.leaflet-overlay-pane path.leaflet-interactive',n=>n.length),263)
    assert.equal(await page.evaluate(()=>sessionStorage.getItem('sigard_admin_token')),null)
    await click('Investigación local A/B')
    await page.waitForSelector('.metric-comparison tbody tr')
    await page.select('#research-model','B')
    await page.waitForFunction(()=>document.querySelector('.research-provenance strong')?.textContent==='Modelo B')
    const radio=await page.$eval('#research-radio',e=>e.options[1].value)
    await page.select('#research-radio',radio)
    await page.waitForSelector('.radio-score-pair')
    await click('Ver evolución temporal')
    await page.waitForSelector('.radio-timeline svg')
    assert.equal(await page.$$eval('.analysis-values tbody tr',n=>n.length),20)
  })
  await check('login protegido, estado inicial y último administrador',async()=>{
    await page.goto(frontendOrigin+'/admin/reportes',{waitUntil:'networkidle0'})
    assert.equal(await page.$('.admin-accounts'),null)
    await login('stage14-admin@example.test','fictitious-initial-password')
    await click('Gestionar cuentas');await accountLoaded()
    assert.equal(await page.$$eval('.account-list tbody tr',n=>n.length),1)
    assert.equal(await page.$eval('button[aria-label="Desactivar stage14-admin@example.test"]',e=>e.disabled),true)
  })
  if(integral || postgis) await check('revisión administrativa del reporte, privacidad y sesión revocada',async()=>{
    await click('Volver a reportes')
    await page.waitForFunction(code=>[...document.querySelectorAll('.report-inbox button')].some(b=>b.textContent.includes(code)),{},trackingCode)
    await fill('.admin-filters input[placeholder="Buscar barrio"]','FICTICIO SIN RESULTADOS')
    await page.waitForFunction(()=>document.querySelector('.report-inbox > header strong')?.textContent==='0 reportes')
    await fill('.admin-filters input[placeholder="Buscar barrio"]','')
    await page.waitForFunction(code=>[...document.querySelectorAll('.report-inbox button')].some(b=>b.textContent.includes(code)),{},trackingCode)
    await page.evaluate(code=>[...document.querySelectorAll('.report-inbox button')].find(b=>b.textContent.includes(code)).click(),trackingCode)
    await page.waitForSelector('.admin-update select')
    await page.select('.admin-update select','en_revision')
    await fill('.admin-update textarea[maxlength="600"]','Reporte ficticio revisado en el entorno de prueba.')
    const saved=page.waitForResponse(r=>r.request().method()==='PATCH' && /admin\/citizen-reports\//.test(r.url()))
    await page.click('.admin-update button[type="submit"], .admin-update .primary-button')
    assert.equal((await saved).status(),200)
    await page.waitForFunction(()=>document.querySelector('.report-detail > header .status-chip')?.textContent==='En revisión')
    const publicStatus=await(await fetch(`${api}/api/v1/citizen-reports/status/${trackingCode}`)).json()
    assert.equal(publicStatus.status,'en_revision')
    assert.ok(!('description' in publicStatus) && !('latitude' in publicStatus))
    assert.equal((await fetch(`${api}/api/v1/admin/citizen-reports`)).status,401)
    const token=await page.evaluate(()=>sessionStorage.getItem('sigard_admin_token'))
    const exported=await fetch(`${api}/api/v1/admin/citizen-reports/export.csv`,{headers:{Authorization:`Bearer ${token}`}})
    assert.equal(exported.status,200)
    assert.equal(exported.headers.get('cache-control'),'no-store')
    assert.ok((await exported.text()).includes(trackingCode))
    if(integral) await accessibility('admin-report-desktop')
    for(const operation of (postgis ? [] : ['detail','save','export'])) {
      rejectReportOperation=operation
      const rejected=page.waitForResponse(r=>[401,403].includes(r.status()) && /admin\/citizen-reports\//.test(r.url()))
      if(operation==='detail') await page.evaluate(code=>[...document.querySelectorAll('.report-inbox button')].find(b=>b.textContent.includes(code)).click(),trackingCode)
      else if(operation==='save') await page.click('.admin-update .primary-button')
      else await click('Exportar CSV')
      await rejected;await delay(150)
      if(!await page.$('.admin-login')) {
        defect('admin-report-revoked-session-'+operation,{context:'Tras rechazo sigue visible el detalle y permanece la sesión local'})
        await click('Cerrar sesión')
      }
      assert.equal(await page.evaluate(()=>sessionStorage.getItem('sigard_admin_token')),null)
      rejectReportOperation=null
      await login('stage14-admin@example.test','fictitious-initial-password')
      await page.waitForFunction(code=>[...document.querySelectorAll('.report-inbox button')].some(b=>b.textContent.includes(code)),{},trackingCode)
      if(operation!=='export') {
        await page.evaluate(code=>[...document.querySelectorAll('.report-inbox button')].find(b=>b.textContent.includes(code)).click(),trackingCode)
        await page.waitForSelector('.admin-update')
      }
    }
    await click('Gestionar cuentas');await accountLoaded()
  })
  await check('creación rechazada sin confirmación correcta y alta autorizada',async()=>{
    await click('Crear cuenta')
    await fill('input[name="email"]','stage14-second@example.test')
    await submitAction('fictitious-wrong-password','fictitious-second-password')
    await page.waitForSelector('.admin-accounts [role="alert"]')
    await page.waitForFunction(()=>document.querySelector('input[name="current_password"]')?.value==='')
    assert.ok(await page.$$eval('.account-operation input[type="password"]',n=>n.every(e=>e.value==='')))
    await submitAction('fictitious-initial-password','fictitious-second-password')
    await page.waitForFunction(()=>document.querySelector('.account-notice')?.textContent.includes('creada'))
    await accountLoaded()
    assert.equal(await page.$$eval('.account-list tbody tr',n=>n.length),2)
  })
  await check('rotación de otra cuenta y rechazo de contraseña anterior',async()=>{
    await page.click('button[aria-label="Rotar contraseña de stage14-second@example.test"]')
    await submitAction('fictitious-initial-password','fictitious-rotated-password')
    await page.waitForFunction(()=>document.querySelector('.account-notice')?.textContent.includes('actualizada'))
    await accountLoaded();await click('Cerrar sesión')
    await login('stage14-second@example.test','fictitious-second-password',false)
    await login('stage14-second@example.test','fictitious-rotated-password')
  })
  await check('rotación propia cierra sesión y exige credencial nueva',async()=>{
    await click('Gestionar cuentas');await accountLoaded()
    await page.click('button[aria-label="Rotar contraseña de stage14-second@example.test"]')
    await submitAction('fictitious-rotated-password','fictitious-final-password')
    await page.waitForSelector('.admin-login [role="status"]')
    assert.equal(await page.evaluate(()=>sessionStorage.getItem('sigard_admin_token')),null)
    await login('stage14-second@example.test','fictitious-rotated-password',false)
    await login('stage14-second@example.test','fictitious-final-password')
  })
  await check('desactivación propia cierra sesión y bloquea login',async()=>{
    await click('Gestionar cuentas');await accountLoaded()
    await page.click('button[aria-label="Desactivar stage14-second@example.test"]')
    await submitAction('fictitious-final-password')
    await page.waitForSelector('.admin-login [role="status"]')
    assert.equal(await page.evaluate(()=>sessionStorage.getItem('sigard_admin_token')),null)
    await login('stage14-second@example.test','fictitious-final-password',false)
    await login('stage14-admin@example.test','fictitious-initial-password')
  })
  await check('error de carga, reintento, lista de estados y retorno a reportes',async()=>{
    failListing=true
    await click('Gestionar cuentas')
    await page.waitForSelector('.admin-accounts [role="alert"]')
    failListing=false
    await click('Reintentar carga');await accountLoaded()
    assert.ok((await page.$eval('.account-list tbody',e=>e.textContent)).includes('Inactiva'))
    await click('Volver a reportes')
    await page.waitForFunction(()=>document.querySelector('.admin-header h1')?.textContent==='Reportes ciudadanos')
    await click('Gestionar cuentas');await accountLoaded()
  })
  await check('escritorio, móvil y formularios sin credenciales visibles',async()=>{
    await mkdir(output,{recursive:true})
    for(const width of [1440,390]) {
      await page.setViewport({width,height:1000})
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
      assert.ok(await page.$eval('.account-list .table-scroll',e=>e.scrollWidth<=e.clientWidth+1))
      if(integral) await accessibility('accounts-'+width)
      await page.screenshot({path:resolve(output,`stage${stage}-accounts-${width}.png`),fullPage:true})
    }
    await click('Crear cuenta')
    assert.ok(await page.$$eval('.account-operation input[type="password"]',n=>n.every(e=>e.value==='')))
    if(integral) await accessibility('account-form-mobile')
    await page.screenshot({path:resolve(output,`stage${stage}-account-form-mobile.png`),fullPage:true})
    await click('Cancelar')
    await click('Cerrar sesión')
  })
  assert.deepEqual(report.pageErrors,[])
  assert.deepEqual(report.reactErrors,[])
  assert.equal(fixtureErrors,'')
  await writeFile(resolve(output,`stage${stage}-browser-result.json`),JSON.stringify(report,null,2))
  console.log(JSON.stringify(report))
  if(integral && process.env.SIGARD_EXPECT_STABLE==='1') assert.deepEqual(report.defects,[])
} finally {
  if(integral || postgis) {await mkdir(output,{recursive:true});await writeFile(resolve(output,`stage${stage}-browser-result.json`),JSON.stringify(report,null,2))}
  await browser?.close()
  fixture.stdin.end('stop\n')
  const cleanExit = await Promise.race([closed.then(()=>true),delay(5000).then(()=>false)])
  if(!cleanExit) fixture.kill()
}
