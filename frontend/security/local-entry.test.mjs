import { after, test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { transformWithOxc } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { isLocalResearchContext } from '../src/services/experimentalContract.mjs'
import { MemoryRouter } from 'react-router-dom'

// Real routes and page, with fictional data and browser-only children replaced.
const url = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const state = { slots: [], cursor: 0, buttons: [], path: '/', enabled: false }
globalThis.__sigardLocalEntry = state
after(() => { delete globalThis.__sigardLocalEntry })
const replacements = {
  react: url(`
    const s=globalThis.__sigardLocalEntry;
    export function useState(initial) {
      const i=s.cursor++;
      if (!(i in s.slots)) s.slots[i]=typeof initial==='function'?initial():initial;
      return [s.slots[i],value=>{s.slots[i]=value}];
    }
    export const useMemo=fn=>fn(),useEffect=()=>{};
  `),
  'react/jsx-runtime': url(`
    import * as r from ${JSON.stringify(new URL('../node_modules/react/jsx-runtime.js', import.meta.url).href)};
    export const Fragment=r.Fragment;
    export function jsx(type,props,key) {
      if(type==='button') globalThis.__sigardLocalEntry.buttons.push(props);
      return r.jsx(type,props,key);
    }
    export const jsxs=r.jsxs;
  `),
  'react-router-dom': url(`
    import React from ${JSON.stringify(new URL('../node_modules/react/index.js', import.meta.url).href)};
    export * from ${JSON.stringify(new URL('../node_modules/react-router-dom/dist/index.mjs', import.meta.url).href)};
    import {MemoryRouter} from ${JSON.stringify(new URL('../node_modules/react-router-dom/dist/index.mjs', import.meta.url).href)};
    export const BrowserRouter=({children})=>React.createElement(MemoryRouter,{initialEntries:[globalThis.__sigardLocalEntry.path]},children);
    export const Navigate=({to,replace})=>React.createElement('div',{'data-redirect':to,'data-replace':String(replace)});
  `),
  './services/localResearch': url('export const localResearchEnabled=()=>globalThis.__sigardLocalEntry.enabled;'),
  './services/demoMode': url('export const demoMode=false;'),
  './services/sigardData': url('export const DATA_ERROR_MESSAGE="fixture error",formatDate=String,loadSigardData=()=>{};'),
  '../services/sigardData': url('export const getSelectedWeek=()=>({}),getSelectedPrediction=()=>({}),getExperimentalCollection=()=>({}),getDisclaimer=()=>"fictional";'),
  '../components/SigardComponents': url('export const MethodNotice=({children})=>children,PageIntro=({title})=>title,TemporalControls=()=>"simulation controls",TerritorialMap=()=>"simulation map";'),
  '../components/HistoricalBacktest': url('export default function Backtest(){return "backtest fixture"}'),
  './App.css': url(''),
  './services/adminSession.mjs': url(`export * from ${JSON.stringify(new URL('../src/services/adminSession.mjs', import.meta.url).href)}`),
}
replacements['../services/localResearch'] = replacements['./services/localResearch']
// The activity probe is disabled here (404 contract): the link must not appear.
replacements['./services/publicActivity.mjs'] = url('export const loadActivity=()=>Promise.resolve({enabled:false});')
for (const page of ['Dashboard', 'Mapa', 'Prevencion', 'AdminArea', 'Actividad']) {
  replacements[`./pages/${page}`] = url(`export default function Page(){return ${JSON.stringify(page)}}`)
}
async function component(path) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8')
  const transformed = await transformWithOxc(source, path, { jsx: { runtime: 'automatic' } })
  const code = transformed.code.replace(/(['"])([^'"]+)\1/g, (original, quote, value) => replacements[value] ? JSON.stringify(replacements[value]) : original)
  return (await import(url(code))).default
}
const App = await component('../src/App.jsx')
const Mapa = await component('../src/pages/Mapa.jsx')
function render(Component, slots = [], props = {}) {
  state.slots = slots; state.cursor = 0; state.buttons = []
  return renderToStaticMarkup(React.createElement(Component, props))
}
const routed = (Component, props) => render(() => React.createElement(MemoryRouter, null, React.createElement(Component, props)))
// Fictional unsigned administrator session (the interface only reads its claims).
const jwt = payload => `h.${Buffer.from(JSON.stringify(payload)).toString('base64url')}.s`
function withSession(token, run) {
  const values = new Map(token ? [['sigard_admin_token', token]] : [])
  globalThis.sessionStorage = { getItem: k => values.get(k) ?? null, removeItem: k => values.delete(k) }
  try { return run() } finally { delete globalThis.sessionStorage }
}

test('root is the public home in every context (no redirect in dev); /dashboard stays reachable locally', () => {
  for (const [dev, origin] of [[true, 'http://127.0.0.1:5173'], [false, 'http://127.0.0.1:5173'], [true, 'http://localhost:5173'], [true, 'https://public.example']]) {
    state.enabled = isLocalResearchContext({ DEV: dev }, origin)
    state.path = '/'
    const slots = [{ availableWeeks: {} }, '2030-01-06', null]
    const html = render(App, slots)
    assert.doesNotMatch(html, /data-redirect|href="\/dashboard"/)
    assert.match(html, /<main>Dashboard<\/main>/)
    assert.match(html, /<a[^>]*href="\/"[^>]*>Situación actual<\/a>/)
    // The home page no longer waits for the MVP publication (only /mapa uses it).
    assert.match(render(App, [null, '', null]), /<main>Dashboard<\/main>/)
    if (state.enabled) {
      state.path = '/dashboard'
      assert.match(render(App, slots), /<main>Dashboard<\/main>/)
    }
  }
})

test('/mapa is always the public map; locally it only links to the viewer in Administración', () => {
  const props = { data: { availableWeeks: { weeks: [] }, territorialContext: {} }, selectedCutoffDate: '2030-01-06' }
  for (const predictiveLink of ['/admin/predictivo?anio=2024&se=12', null]) {
    const html = routed(Mapa, { ...props, predictiveLink })
    assert.match(html, /Mapa público agregado/)
    assert.doesNotMatch(html, /backtest fixture|Predicción semanal de dengue por radio censal|research fixture/)
    if (predictiveLink) assert.match(html, /<a href="\/admin\/predictivo\?anio=2024&amp;se=12"[^>]*>El módulo predictivo está en Administración<\/a>/)
    else assert.doesNotMatch(html, /módulo predictivo/i)
  }
})

test('public menu has no predictive module; old /mapa viewer links redirect only with an administrator session', () => {
  const slots = [{ availableWeeks: {} }, '2030-01-06', null]
  const future = Math.floor(Date.now() / 1000) + 600
  for (const enabled of [true, false]) {
    state.enabled = enabled; state.path = '/mapa'
    const html = withSession('', () => render(App, slots))
    assert.match(html, /href="\/mapa"[^>]*>Mapa público</); assert.doesNotMatch(html, />Módulo predictivo</)
    assert.match(html, /<main>Mapa<\/main>/); assert.doesNotMatch(html, /data-redirect/)
  }
  state.enabled = true
  const link = '/mapa?anio=2024&se=12&vista=cuantos&metodo=comparar&capa=observados&radio=123456789&modelo=residual_v2'
  state.path = link
  const redirected = withSession(jwt({ role: 'admin', exp: future }), () => render(App, slots))
  assert.match(redirected, /data-redirect="\/admin\/predictivo\?anio=2024&amp;se=12&amp;vista=cuantos&amp;metodo=comparar&amp;capa=observados&amp;radio=123456789&amp;modelo=residual_v2" data-replace="true"/)
  // No session, an expired one or a non-admin role: the public map stays (with the link to Administración).
  for (const token of ['', jwt({ role: 'admin', exp: future - 1200 }), jwt({ role: 'operador', exp: future })])
    assert.doesNotMatch(withSession(token, () => render(App, slots)), /data-redirect/)
  // A plain /mapa (no viewer state) never redirects, even with a session; production never does.
  state.path = '/mapa'; assert.doesNotMatch(withSession(jwt({ role: 'admin', exp: future }), () => render(App, slots)), /data-redirect/)
  state.enabled = false; state.path = link; assert.doesNotMatch(withSession(jwt({ role: 'admin', exp: future }), () => render(App, slots)), /data-redirect/)
})

test('F7b: no source file calls the retired research API on 8765 or imports the removed A/B pages', async () => {
  const { readdir } = await import('node:fs/promises')
  const root = new URL('../src/', import.meta.url)
  const files = (await readdir(root, { recursive: true })).filter(name => /\.(m?jsx?|css)$/.test(name))
  assert.ok(files.length > 30)
  for (const name of files) {
    const source = await readFile(new URL(name.split(String.fromCharCode(92)).join('/'), root), 'utf8')
    assert.doesNotMatch(source, /8765|research\/spatial|ExperimentalSpatial|ExperimentalAnalysis|experimentalResults/, name)
  }
})


test('the Validación and Cómo funciona pages are gone: not in the menu, old URLs go to the home page', async () => {
  const slots = [{ availableWeeks: {} }, '2030-01-06', null]
  for (const enabled of [true, false]) {
    state.enabled = enabled; state.path = '/'
    const html = render(App, slots)
    const menu = html.match(/<nav class="main-nav"[^]*?<\/nav>/)[0]
    assert.deepEqual([...menu.matchAll(/>([^<>]+)<\/a>/g)].map(m => m[1]), ['Situación actual', 'Mapa público', 'Prevención y ayuda', 'Administración'])
    assert.doesNotMatch(html, /href="\/(validacion|metodologia)"|>Validación<|>Cómo funciona</)
    for (const path of ['/validacion', '/metodologia']) {
      state.path = path
      assert.match(render(App, slots), /<div data-redirect="\/" data-replace="true"><\/div>/, path)
    }
  }
  const { readdir } = await import('node:fs/promises')
  const pages = await readdir(new URL('../src/pages/', import.meta.url))
  assert.ok(!pages.includes('Validacion.jsx') && !pages.includes('Metodologia.jsx'))
})
