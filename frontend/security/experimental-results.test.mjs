import { test } from 'node:test'
import assert from 'node:assert/strict'
import { experimentalColor, isLocalResearchContext, validateCatalog, validateScores, validateComparison, joinExperimentalGeometry } from '../src/services/experimentalContract.mjs'

const schema = 'sigard-retrospective-spatial-score/1'
const models = ['A', 'B'].map(id => ({ model_id: id,
  experiment_id: id === 'A' ? 'spatial_rf_05c_v1' : 'spatial_rf_B_05f_v1',
  training_version: id === 'A' ? 'official-spatial-rf-research-0.5c.0' : 'official-spatial-rf-B-research-0.5f.0' }))
function collection(id = 'A', score = .2) {
  return { schema_version: schema, ...models.find(m => m.model_id === id), target_week_start: '2024-01-07',
    territory_version: 'capital-census-2022-public-v1', calendar_version: 'ar-snvs-2020-2026-v1',
    data_kind: 'official_experimental_retrospective', score_semantics: 'raw_class_1_score_uncalibrated',
    retrospective: true, operational_use_authorized: false, publication_authorized: false,
    coverage_verified: false, previously_examined: true, coverage_scenario: 'spatial_assumed_2024_v1',
    interpretation_limitations: Array(10).fill('fictional'), rows: [{ radio_censal: '000001',
      experimental_score: score, score_status: score === null ? 'not_computed' : 'available',
      score_unavailable_reason: score === null ? 'frozen_score_missing' : null,
      data_availability: { prediction_as_of: null, operational_availability: 'not_accredited' } }] }
}

test('experimental mode is automatic only in development at the exact loopback origin', () => {
  assert.equal(isLocalResearchContext({ DEV: true }, 'http://127.0.0.1:5173'), true)
  for (const env of [{}, { DEV: false }, { DEV: false, VITE_LOCAL_RESEARCH: 'true' }]) {
    assert.equal(isLocalResearchContext(env, 'http://127.0.0.1:5173'), false)
  }
  for (const origin of ['https://public.example', 'http://localhost:5173', 'http://192.0.2.1:5173']) {
    assert.equal(isLocalResearchContext({ DEV: true }, origin), false)
  }
})

test('missing score differs from zero; raw color boundaries are deterministic', () => {
  assert.notEqual(experimentalColor(null), experimentalColor(0))
  assert.equal(experimentalColor(1), experimentalColor(.75))
  assert.notEqual(experimentalColor(.2499), experimentalColor(.25))
  validateScores(collection('A', null), models[0], '2024-01-07', ['000001'])
  validateScores(collection('A', 0), models[0], '2024-01-07', ['000001'])
})

test('wrong model, version, date, radio, missing status and nonfinite scores fail closed', () => {
  for (const change of [c => c.model_id = 'B', c => c.training_version = 'new', c => c.target_week_start = '2024-01-14',
    c => c.rows[0].radio_censal = '1', c => c.rows[0].experimental_score = NaN,
    c => c.rows[0].experimental_score = null, c => c.coverage_verified = true]) {
    const c = collection(); change(c)
    assert.throws(() => validateScores(c, models[0], '2024-01-07', ['000001']))
  }
  assert.throws(() => validateCatalog({ schema_version: schema, models: [{ ...models[0], weeks: [] }] }))
})

test('A/B comparison requires equivalent identities and two available scores', () => {
  const value = { schema_version: schema, radio_censal: '000001', target_week_start: '2024-01-07', comparable: true,
    results: [collection(), collection('B', .4)] }
  validateComparison(value, { models }, '000001', '2024-01-07')
  value.results[1] = collection('B', null)
  assert.throws(() => validateComparison(value, { models }, '000001', '2024-01-07'))
  value.comparable = false
  validateComparison(value, { models }, '000001', '2024-01-07')
  value.results[1].target_week_start = '2024-01-14'
  assert.throws(() => validateComparison(value, { models }, '000001', '2024-01-07'))
})

test('map joins by canonical radio and updates scores and target when the selection changes', () => {
  const geometry = { type: 'FeatureCollection', features: ['000001', '000002', '000003'].map(id => ({
    type: 'Feature', geometry: { type: 'Polygon', coordinates: [] }, properties: { radio_id: id },
  })) }
  const a = collection()
  a.rows = [
    { radio_censal: '000003', experimental_score: null, score_status: 'not_computed' },
    { radio_censal: '000002', experimental_score: .8, score_status: 'available' },
    { radio_censal: '000001', experimental_score: 0, score_status: 'available' },
  ]
  const first = joinExperimentalGeometry(geometry, a)
  assert.deepEqual(first.features.map(f => f.properties.experimental_score), [0, .8, null])
  assert.notEqual(experimentalColor(first.features[0].properties.experimental_score), experimentalColor(first.features[2].properties.experimental_score))
  const b = { ...a, model_id: 'B', target_week_start: '2024-01-14',
    rows: a.rows.map(row => ({ ...row, experimental_score: .4, score_status: 'available' })) }
  const next = joinExperimentalGeometry(geometry, b)
  assert.ok(next.features.every(f => f.properties.experimental_score === .4 && f.properties.target_week_start === '2024-01-14'))
  assert.deepEqual(first.features.map(f => f.properties.experimental_score), [0, .8, null])
  assert.ok(geometry.features.every(f => Object.keys(f.properties).length === 1))
})

test('research map uses the city view, retains all radios and stays mounted while scores load', async () => {
  // Render the real component with Leaflet controls stubbed; no browser, network or private data.
  const { readFile } = await import('node:fs/promises')
  const { transformWithOxc } = await import('vite')
  const React = await import('react')
  const { renderToStaticMarkup } = await import('react-dom/server')
  const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
  const state = { mapProps: null, layer: null, reset: null, fitElements: 0, calls: [] }
  state.map = { setView: (...args) => state.calls.push(['setView', ...args]), fitBounds: (...args) => state.calls.push(['fitBounds', ...args]) }
  globalThis.__sigardMapViewTest = state
  const runtime = moduleUrl(`
    import * as actual from ${JSON.stringify(new URL('../node_modules/react/jsx-runtime.js', import.meta.url).href)};
    export const Fragment = actual.Fragment;
    function capture(type, props) {
      if (type?.name === 'FitBounds') globalThis.__sigardMapViewTest.fitElements++;
      if (props?.className === 'map-reset') globalThis.__sigardMapViewTest.reset = props.onClick;
    }
    export function jsx(type,props,key) { capture(type,props); return actual.jsx(type,props,key) }
    export function jsxs(type,props,key) { capture(type,props); return actual.jsxs(type,props,key) }
  `)
  const replacements = {
    react: new URL('../node_modules/react/index.js', import.meta.url).href,
    'react/jsx-runtime': runtime,
    'react-leaflet': moduleUrl(`
      export function MapContainer(props) { globalThis.__sigardMapViewTest.mapProps=props; return props.children }
      export function GeoJSON(props) { globalThis.__sigardMapViewTest.layer=props; return null }
      export function useMap() { return globalThis.__sigardMapViewTest.map }
    `),
    leaflet: moduleUrl('export default {geoJSON:()=>({getBounds:()=>({isValid:()=>true})})}'),
    'leaflet/dist/leaflet.css': moduleUrl('export {}'),
    '../services/sigardData': moduleUrl('export const formatDate=String,formatDateRange=String,formatNumber=String,levelColors={},levelLabel=String'),
    '../services/experimentalContract.mjs': new URL('../src/services/experimentalContract.mjs', import.meta.url).href,
  }
  try {
    const source = await readFile(new URL('../src/components/SigardComponents.jsx', import.meta.url), 'utf8')
    const transformed = await transformWithOxc(source, 'SigardComponents.jsx', { jsx: { runtime: 'automatic' } })
    const code = transformed.code.replace(/(['"])([^'"]+)\1/g, (original, quote, value) => replacements[value] ? JSON.stringify(replacements[value]) : original)
    const { TerritorialMap } = await import(moduleUrl(code))
    const geojson = { type: 'FeatureCollection', features: Array.from({ length: 263 }, (_, i) => ({
      type: 'Feature', properties: { radio_id: String(i), experimental_score: 0 }, geometry: { type: 'Polygon', coordinates: [] },
    })) }
    for (const [key, showData] of [['A/first', true], ['B/first', false], ['B/first', true], ['B/next', false], ['B/next', true]]) {
      state.mapProps = null; state.layer = null; state.fitElements = 0
      const markup = renderToStaticMarkup(React.createElement(TerritorialMap, { geojson, view: 'research', collectionKey: key, showData }))
      assert.deepEqual(state.mapProps.center, [-29.418, -66.856])
      assert.equal(state.mapProps.zoom, 13)
      assert.equal(state.mapProps.bounds, undefined)
      assert.equal(state.mapProps.maxBounds, undefined)
      assert.equal(state.fitElements, 0)
      assert.deepEqual(state.calls, [])
      if (showData) assert.equal(state.layer.data.features.length, 263)
      else { assert.equal(state.layer, null); assert.match(markup, /Consultando scores/) }
    }
    state.reset()
    assert.deepEqual(state.calls, [['setView', [-29.418, -66.856], 13]])
    // The MVP keeps its existing full-territory reset behavior.
    state.calls = []; state.fitElements = 0
    renderToStaticMarkup(React.createElement(TerritorialMap, { geojson, view: 'simulation' }))
    assert.equal(state.mapProps.center, undefined)
    assert.equal(state.fitElements, 1)
    state.reset()
    assert.equal(state.calls[0][0], 'fitBounds')
  } finally {
    delete globalThis.__sigardMapViewTest
  }
})

test('research requests read aggregates directly without cookies, tokens or approval calls', async () => {
  const { readFile } = await import('node:fs/promises')
  let source = await readFile(new URL('../src/services/experimentalResults.js', import.meta.url), 'utf8')
  source = source.replace('import.meta.env.DEV', 'true')
    .replace("'./experimentalContract.mjs'", JSON.stringify(new URL('../src/services/experimentalContract.mjs', import.meta.url).href))
    .replace("'./experimentalAnalysis.mjs'", JSON.stringify(new URL('../src/services/experimentalAnalysis.mjs', import.meta.url).href))
  const previousFetch = globalThis.fetch, previousWindow = globalThis.window
  const calls = []
  const catalog = { schema_version: schema, models: models.map(m => ({ ...m, weeks: Array.from({ length: 20 }, (_, i) => ({ target_week_start: `2024-01-${String(i + 1).padStart(2, '0')}`, target_epidemiological_week: i + 1 })) })) }
  let responses = [[200, catalog], [200, collection()], [200, { comparable: true }], [503, {}], [403, {}]]
  globalThis.window = { location: { origin: 'http://127.0.0.1:5173' } }
  globalThis.fetch = async (url, options) => {
    calls.push({ url, ...options })
    const [status, body] = responses.shift()
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const service = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
    assert.deepEqual(await service.researchCatalog(), catalog)
    assert.deepEqual(await service.researchScores(models[0], '2024-01-07', ['000001']), collection())
    await service.researchRequest('/comparison/2024-01-07/000001')
    await assert.rejects(() => service.researchRequest('/models'), error => error.status === 503 && /integridad/.test(error.message))
    await assert.rejects(() => service.researchRequest('/models'), error => error.status === 403 && /equipo local/.test(error.message))
    for (const call of calls) {
      assert.equal(call.method, 'GET')
      assert.equal(call.credentials, 'omit')
      assert.equal(call.cache, 'no-store')
      assert.equal(call.redirect, 'error')
      assert.equal(call.headers['X-Sigard-Research'], 'local-read')
      assert.equal(call.headers.Authorization, undefined)
      assert.equal(call.body, undefined)
      assert.ok(!call.url.includes('/session'))
    }
    assert.deepEqual(responses, [])
    globalThis.window.location.origin = 'https://foreign.example'
    await assert.rejects(() => service.researchCatalog(), /desarrollo local/)
    assert.equal(calls.length, 5)
  } finally {
    globalThis.fetch = previousFetch
    if (previousWindow === undefined) delete globalThis.window
    else globalThis.window = previousWindow
  }
})

test('experimental selectors and radio comparison work after automatic catalog loading', async () => {
  const { readFile } = await import('node:fs/promises')
  const { transformWithOxc } = await import('vite')
  const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
  const weeks = Array.from({ length: 20 }, (_, i) => ({
    target_week_start: new Date(Date.UTC(2024, 0, 7 + i * 7)).toISOString().slice(0, 10),
    target_epidemiological_year: 2024, target_epidemiological_week: i + 2,
  }))
  const catalog = { schema_version: schema, models: models.map(m => ({ ...m, weeks })) }
  const radios = Array.from({ length: 263 }, (_, i) => String(i).padStart(6, '0'))
  const geometry = { type: 'FeatureCollection', features: radios.map(id => ({
    type: 'Feature', geometry: { type: 'Polygon', coordinates: [] }, properties: { radio_id: id },
  })) }
  const state = { slots: [], cursor: 0, effects: [], dirty: true, calls: [], failCatalog: true }
  state.catalog = async () => {
    state.calls.push('/models')
    if (state.failCatalog) throw Error('API no disponible')
    return catalog
  }
  state.scores = async (model, week, ids) => {
    state.calls.push(`${model.model_id}/${week}`)
    assert.deepEqual(ids, radios)
    return { ...collection(model.model_id, model.model_id === 'A' ? .2 : .4), target_week_start: week,
      rows: ids.map(id => ({ ...collection(model.model_id).rows[0], radio_censal: id,
        experimental_score: model.model_id === 'A' ? .2 : .4 })) }
  }
  state.request = async path => {
    state.calls.push(path)
    const [, , week, radio] = path.split('/')
    return { schema_version: schema, radio_censal: radio, target_week_start: week, comparable: true,
      results: models.map(m => ({ ...collection(m.model_id, m.model_id === 'A' ? .2 : .4), target_week_start: week,
        rows: [{ ...collection(m.model_id, m.model_id === 'A' ? .2 : .4).rows[0], radio_censal: radio }] })) }
  }
  globalThis.__sigardExperimentalFlow = state
  const replacements = {
    react: moduleUrl(`
      const state = globalThis.__sigardExperimentalFlow;
      export function useState(initial) {
        const i = state.cursor++;
        if (!(i in state.slots)) state.slots[i] = initial;
        return [state.slots[i], next => {
          state.slots[i] = typeof next === 'function' ? next(state.slots[i]) : next;
          state.dirty = true;
        }];
      }
      export const useMemo = fn => fn();
      export function useEffect(fn, deps) {
        const i = state.cursor++, previous = state.slots[i];
        if (!previous || deps.some((value, j) => !Object.is(value, previous.deps[j]))) {
          state.effects.push(() => {
            previous?.cleanup?.();
            state.slots[i] = { deps, cleanup: fn() };
          });
        }
      }
    `),
    'react/jsx-runtime': moduleUrl('export const Fragment="fragment"; export const jsx=(type,props)=>({type,props}); export const jsxs=jsx;'),
    './SigardComponents': moduleUrl('export const TerritorialMap="map",MethodNotice="notice";'),
    './ExperimentalAnalysis': moduleUrl('export default function ExperimentalAnalysis(){return null}'),
    '../services/experimentalAnalysis.mjs': new URL('../src/services/experimentalAnalysis.mjs', import.meta.url).href,
    '../services/experimentalContract.mjs': new URL('../src/services/experimentalContract.mjs', import.meta.url).href,
    '../services/experimentalResults': moduleUrl(`
      const s=globalThis.__sigardExperimentalFlow;
      export const researchCatalog=s.catalog,researchScores=s.scores,researchRequest=s.request;
    `),
    '../services/sigardData': moduleUrl('export const formatNumber=String;'),
  }
  try {
    const source = await readFile(new URL('../src/components/ExperimentalSpatial.jsx', import.meta.url), 'utf8')
    const transformed = await transformWithOxc(source, 'ExperimentalSpatial.jsx', { jsx: { runtime: 'automatic' } })
    const code = transformed.code.replace(/(['"])([^'"]+)\1/g, (original, quote, value) => replacements[value] ? JSON.stringify(replacements[value]) : original)
    const { default: Component } = await import(moduleUrl(code))
    let tree
    async function settle() {
      for (let i = 0; i < 10; i++) {
        if (state.dirty) {
          state.cursor = 0; state.dirty = false
          tree = Component({ geometry })
          for (const effect of state.effects.splice(0)) effect()
        }
        await new Promise(resolve => setImmediate(resolve))
        if (!state.dirty) return
      }
      assert.fail('Component did not settle')
    }
    function nodes(node) {
      if (Array.isArray(node)) return node.flatMap(child => nodes(child))
      if (!node || typeof node !== 'object') return []
      return [node, ...nodes(node.props?.children)]
    }
    const find = predicate => nodes(tree).find(predicate)
    await settle()
    assert.deepEqual(state.calls, ['/models'])
    assert.ok(find(n => n.props?.role === 'alert'))
    const retry = find(n => n.type === 'button')
    assert.equal(retry.props.children, 'Reintentar carga')
    state.failCatalog = false
    retry.props.onClick()
    await settle()
    assert.equal(find(n => n.type === 'map').props.geojson.features.length, 263)
    assert.equal(find(n => n.props?.id === 'research-model').props.value, 'A')
    for (const id of ['B', 'A']) {
      find(n => n.props?.id === 'research-model').props.onChange({ target: { value: id } })
      await settle()
      for (const week of weeks) {
        find(n => n.props?.id === 'research-week').props.onChange({ target: { value: week.target_week_start } })
        await settle()
        const map = find(n => n.type === 'map')
        assert.equal(map.props.showData, true)
        assert.ok(map.props.geojson.features.every(f => f.properties.target_week_start === week.target_week_start && f.properties.experimental_score === (id === 'A' ? .2 : .4)))
      }
    }
    find(n => n.type === 'map').props.onRadioSelect(radios[2])
    await settle()
    assert.equal(state.calls.at(-1), `/comparison/${weeks.at(-1).target_week_start}/${radios[2]}`)
    const details = JSON.stringify(find(n => n.type === 'map').props.researchDetails)
    assert.ok(details.includes('Modelo ') && details.includes('0.2') && details.includes('0.4'))
    assert.ok(!JSON.stringify(tree).match(/Autorizar|Windows|contraseña|token|Desconectar/))
    assert.ok(!state.calls.some(path => path.includes('/session')))
  } finally {
    for (const slot of state.slots) slot?.cleanup?.()
    delete globalThis.__sigardExperimentalFlow
  }
})
