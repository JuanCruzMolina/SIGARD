import { after, test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { transformWithOxc } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { isLocalResearchContext } from '../src/services/experimentalContract.mjs'

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
  './services/experimentalResults': url('export const localResearchEnabled=()=>globalThis.__sigardLocalEntry.enabled;'),
  './services/demoMode': url('export const demoMode=false;'),
  './services/sigardData': url('export const DATA_ERROR_MESSAGE="fixture error",formatDate=String,loadSigardData=()=>{};'),
  '../services/sigardData': url('export const getSelectedWeek=()=>({}),getSelectedPrediction=()=>({}),getExperimentalCollection=()=>({}),getDisclaimer=()=>"fictional";'),
  '../components/SigardComponents': url('export const MethodNotice=({children})=>children,PageIntro=({title})=>title,TemporalControls=()=>"simulation controls",TerritorialMap=()=>"simulation map";'),
  '../components/ExperimentalSpatial': url('export default function Research(){return "research fixture"}'),
  './App.css': url(''),
}
replacements['../services/experimentalResults'] = replacements['./services/experimentalResults']
for (const page of ['Dashboard', 'Mapa', 'Validacion', 'Metodologia', 'Prevencion', 'AdminReports']) {
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

test('root redirects with replace only in authorized local development; dashboard remains reachable', () => {
  for (const [dev, origin] of [[true, 'http://127.0.0.1:5173'], [false, 'http://127.0.0.1:5173'], [true, 'http://localhost:5173'], [true, 'https://public.example']]) {
    state.enabled = isLocalResearchContext({ DEV: dev }, origin)
    state.path = '/'
    const slots = [{ availableWeeks: {} }, '2030-01-06', null]
    const html = render(App, slots)
    if (state.enabled) {
      assert.match(html, /data-redirect="\/mapa" data-replace="true"/)
      assert.match(html, /href="\/dashboard"/)
      state.path = '/dashboard'
      assert.match(render(App, slots), /<main>Dashboard<\/main>/)
    } else {
      assert.doesNotMatch(html, /data-redirect|href="\/dashboard"/)
      assert.match(html, /<main>Dashboard<\/main>/)
    }
  }
})

test('map starts in research locally, allows both manual switches, and keeps public simulation', () => {
  const props = { data: { availableWeeks: { weeks: [] }, territorialContext: {} }, selectedCutoffDate: '2030-01-06' }
  state.enabled = true
  assert.match(render(Mapa, [], props), /research fixture/)
  assert.equal(state.buttons[1]['aria-pressed'], true)
  state.buttons[0].onClick()
  assert.doesNotMatch(render(Mapa, state.slots, props), /research fixture/)
  assert.equal(state.buttons[0]['aria-pressed'], true)
  state.buttons[1].onClick()
  assert.match(render(Mapa, state.slots, props), /research fixture/)
  state.enabled = false
  const publicHtml = render(Mapa, [], props)
  assert.match(publicHtml, /Mapa público agregado/)
  assert.doesNotMatch(publicHtml, /research fixture|research-mode/)
})
