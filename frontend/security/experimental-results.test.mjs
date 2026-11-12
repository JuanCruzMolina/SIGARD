import { test } from 'node:test'
import assert from 'node:assert/strict'
import { differenceColor, scoreDifference, joinComparisonGeometry, experimentalColor, isLocalResearchContext, validateCatalog, validateScores, validateComparison, joinExperimentalGeometry, validateResolvedDate, validateDateQuery } from '../src/services/experimentalContract.mjs'

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

test('calendar and partition metadata must match before comparing frozen scores', () => {
  const meta = { target_week_start: '2024-01-07', target_week_end: '2024-01-13', target_epidemiological_year: 2024, target_epidemiological_week: 2, evaluation_partition: 'train' }
  const model = { ...models[0], weeks: [meta] }
  const value = { ...collection(), ...meta }
  validateScores(value, model, meta.target_week_start, ['000001'])
  for (const field of ['target_week_end', 'target_epidemiological_year', 'target_epidemiological_week', 'evaluation_partition']) {
    assert.throws(() => validateScores({ ...value, [field]: 'incompatible' }, model, meta.target_week_start, ['000001']))
  }
  const catalog = { schema_version: schema, models: models.map(m => ({ ...m, weeks: Array.from({ length: 20 }, (_, i) => ({ ...meta, target_week_start: `2024-01-${String(i + 1).padStart(2, '0')}` })) })) }
  validateCatalog(catalog)
  catalog.models[1].weeks[0].evaluation_partition = 'test'
  assert.throws(() => validateCatalog(catalog))
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
    '../services/predictivePresentation.mjs': new URL('../src/services/predictivePresentation.mjs', import.meta.url).href,
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
    .replace("import { demoMode } from './demoMode'", 'const demoMode = false')
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
    globalThis.fetch = async () => { throw new TypeError('fictional disconnect') }
    await assert.rejects(() => service.researchRequest('/models'), /No se pudo contactar/)
    globalThis.fetch = async () => new Response('incomplete fictional JSON')
    await assert.rejects(() => service.researchRequest('/models'), /respuesta incompleta/)
    const controller = new AbortController()
    const superseded = new Error('obsolete request')
    controller.abort(superseded)
    globalThis.fetch = async (_url, options) => { throw options.signal.reason }
    await assert.rejects(() => service.researchRequest('/models', controller.signal), error => error === superseded)
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
  const offsets = [...Array(8).keys(), ...Array.from({ length: 8 }, (_, i) => i + 9), ...Array.from({ length: 4 }, (_, i) => i + 18)]
  const weeks = offsets.map((offset, i) => ({
    target_week_start: new Date(Date.UTC(2024, 0, 7 + offset * 7)).toISOString().slice(0, 10),
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
  state.date = async requested => {
    if (state.pauseDates) await new Promise(resolve => state.pendingDates.push({ requested, resolve }))
    const day = new Date(requested + 'T00:00:00Z')
    const start = new Date(day); start.setUTCDate(day.getUTCDate() - day.getUTCDay())
    const add = n => new Date(start.getTime() + n * 86400000).toISOString().slice(0, 10)
    return { requested_date: requested, target_week_start: add(0), target_week_end: add(6), origin_week_start: add(-7), origin_week_end: add(-1), calendar_cutoff: add(-1), target_epidemiological_year: 2024, target_epidemiological_week: 2, calendar_min: '2019-12-29', calendar_max: '2027-01-02' }
  }
  state.scores = async (model, date, ids, temporal) => {
    const week = temporal.target_week_start
    state.calls.push(`${model.model_id}/${week}`)
    assert.deepEqual(ids, radios)
    if (state.pauseScores) await new Promise(resolve => state.pending.push({ week, model: model.model_id, resolve }))
    if (state.failModel === model.model_id) throw Error('Error ficticio de scores')
    if (!weeks.some(w => w.target_week_start === week)) return { result: null, blockers: ['no_frozen_prediction', 'temporal_provenance_not_verified'] }
    return { blockers: [], result: { ...collection(model.model_id, model.model_id === 'A' ? .2 : .4), target_week_start: week,
      rows: ids.map(id => ({ ...collection(model.model_id).rows[0], radio_censal: id,
        experimental_score: model.model_id === 'A' ? .2 : .4 })) } }
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
      export const researchCatalog=s.catalog,researchDate=s.date,researchDateQuery=s.scores;
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
    async function chooseDate(value, submit = true) {
      find(n => n.props?.id === 'research-date').props.onChange({ target: { value } })
      await settle()
      assert.ok(find(n => n.type === 'map').props.geojson.features.every(f => f.properties.experimental_score === null && f.properties.difference === null), 'editing date clears all previous scores immediately')
      if (submit) { find(n => n.type === 'button' && n.props.children === 'Consultar predicción').props.onClick(); await settle() }
    }
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
    assert.ok(!state.calls.some(call => call.startsWith('A/')), 'predictions require explicit submission')
    for (const id of ['B', 'A']) {
      find(n => n.props?.id === 'research-model').props.onChange({ target: { value: id } })
      await settle()
      for (const week of weeks) {
        await chooseDate(week.target_week_start)
        const map = find(n => n.type === 'map')
        assert.ok(map.props.geojson.features.every(f => f.properties.target_week_start === week.target_week_start && f.properties.experimental_score === (id === 'A' ? .2 : .4)))
      }
    }
    find(n => n.type === 'map').props.onRadioSelect(radios[2])
    await settle()
    const count = state.calls.length
    assert.equal(find(n => n.props?.id === 'research-radio').props.value, radios[2])
    let details = find(n => n.type === 'map').props.researchDetails
    assert.equal(details.props.feature.properties.model_a.experimental_score, .2)
    assert.equal(details.props.feature.properties.model_b.experimental_score, .4)
    for (const mode of ['difference', 'B', 'A', 'difference']) {
      find(n => n.props?.id === 'research-model').props.onChange({ target: { value: mode } })
      await settle()
      assert.equal(find(n => n.props?.id === 'research-date').props.value, weeks.at(-1).target_week_start)
      assert.equal(find(n => n.type === 'map').props.geojson.features[2].properties.difference, .2)
    }
    find(n => n.props?.id === 'research-radio').props.onChange({ target: { value: radios[1] } })
    await settle()
    assert.equal(find(n => n.type === 'map').props.selectedRadio, radios[1])
    assert.equal(state.calls.length, count, 'mode and radio reuse the validated weekly collections')

    // Resolve superseded requests after the latest ones; the stub deliberately ignores abort.
    state.pauseScores = true; state.pending = []
    await chooseDate(weeks[0].target_week_start)
    assert.ok(find(n => n.type === 'map').props.geojson.features.every(f => f.properties.experimental_score === null))
    await chooseDate(weeks[1].target_week_start)
    assert.equal(state.pending.length, 4)
    state.pending.slice(2).forEach(p => p.resolve())
    await settle()
    assert.equal(find(n => n.type === 'map').props.geojson.features[1].properties.model_a.experimental_score, .2)
    state.pending.slice(0, 2).forEach(p => p.resolve())
    await settle()
    assert.ok(find(n => n.type === 'map').props.geojson.features.every(f => f.properties.target_week_start === weeks[1].target_week_start))

    state.pauseScores = false; state.failModel = 'B'
    await chooseDate(weeks[2].target_week_start)
    const partial = find(n => n.type === 'map').props.geojson.features[1].properties
    assert.equal(partial.model_a.experimental_score, .2)
    assert.equal(partial.model_b, undefined)
    assert.equal(partial.difference, null)
    assert.ok(find(n => n.props?.role === 'alert'))
    state.failModel = null
    find(n => n.type === 'button' && n.props.children === 'Reintentar consulta').props.onClick()
    await settle()
    assert.equal(find(n => n.type === 'map').props.geojson.features[1].properties.difference, .2)
    assert.equal(find(n => n.props?.role === 'alert'), undefined)
    await chooseDate('2024-03-06')
    assert.equal(find(n => n.type === 'map').props.selectedRadio, radios[1])
    assert.ok(find(n => n.type === 'map').props.geojson.features.every(f => f.properties.difference === null && f.properties.score_status === 'not_computed'))
    for (const requested of ['2024-04-07', '2024-04-10', '2024-04-13']) {
      await chooseDate(requested)
      assert.equal(find(n => n.type === 'map').props.geojson.features[1].properties.target_week_start, '2024-04-07')
      assert.equal(find(n => n.type === 'map').props.geojson.features[1].properties.difference, .2)
      assert.equal(find(n => n.type === 'map').props.selectedRadio, radios[1])
    }
    state.pauseDates = true; state.pendingDates = []
    await chooseDate('2024-04-14', false)
    await chooseDate('2024-04-21', false)
    state.pendingDates[1].resolve(); await settle()
    assert.equal(find(n => n.type === 'map').props.geojson.features[0].properties.target_week_start, '2024-04-21')
    state.pendingDates[0].resolve(); await settle()
    assert.equal(find(n => n.type === 'map').props.geojson.features[0].properties.target_week_start, '2024-04-21')
    assert.ok(!JSON.stringify(tree).match(/Autorizar|Windows|contraseña|token|Desconectar/))
    assert.ok(!state.calls.some(path => path.includes('/session')))
  } finally {
    for (const slot of state.slots) slot?.cleanup?.()
    delete globalThis.__sigardExperimentalFlow
  }
})

test('difference has fixed divergent signs, real zero and missing values; source rows stay intact', () => {
  const row = value => ({ score_status: value === null ? 'not_computed' : 'available', experimental_score: value })
  for (const [a, b, expected] of [[.25, .75, .5], [.75, .25, -.5], [0, 0, 0], [1, 0, -1], [0, 1, 1], [null, 0, null], [1, null, null]]) {
    assert.equal(scoreDifference(row(a), row(b)), expected)
  }
  assert.equal(scoreDifference(undefined, row(0)), null)
  assert.equal(new Set([differenceColor(-1), differenceColor(-.5), differenceColor(0), differenceColor(.5), differenceColor(1), differenceColor(null)]).size, 6)
  assert.equal(differenceColor(-.5), differenceColor(-.001))
  assert.equal(differenceColor(.5), differenceColor(.001))
  const geometry = { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Polygon', coordinates: [] }, properties: { radio_id: '000001' } }] }
  const values = { A: { value: collection('A', 0) }, B: { value: collection('B', null) } }
  const before = structuredClone({ geometry, values })
  const joined = joinComparisonGeometry(geometry, values, '2024-01-07', 'difference')
  assert.equal(joined.features[0].properties.difference, null)
  assert.deepEqual({ geometry, values }, before)
  assert.equal(joinComparisonGeometry(geometry, values, '2024-01-07', 'A').features[0].properties.experimental_score, 0)
})

test('date query validates t+1, model identity, unchanged frozen metadata and explicit unavailability', () => {
  const temporal = { schema_version: 'sigard-private-spatial-date-query/1', requested_date: '2024-01-10',
    calendar_version: 'ar-snvs-2020-2026-v1', calendar_min: '2019-12-29', calendar_max: '2027-01-02',
    calendar_status: 'supported', horizon_weeks: 1, information_cutoff: null,
    operational_use_authorized: false, publication_authorized: false,
    target_week_start: '2024-01-07', target_week_end: '2024-01-13', target_epidemiological_year: 2024, target_epidemiological_week: 2,
    origin_week_start: '2023-12-31', origin_week_end: '2024-01-06', calendar_cutoff: '2024-01-06' }
  validateResolvedDate(temporal, temporal.requested_date)
  const value = { ...temporal, ...models[0], territory_version: 'capital-census-2022-public-v1', radio_ids: ['000001'],
    new_inference_enabled: false, availability: 'available', result_type: 'frozen', blockers: [],
    result: { ...collection(), ...Object.fromEntries(['target_week_end', 'target_epidemiological_year', 'target_epidemiological_week', 'origin_week_start', 'origin_week_end'].map(k => [k, temporal[k]])) } }
  validateDateQuery(value, temporal.requested_date, models[0], ['000001'], temporal)
  for (const change of [v => v.requested_date = '2024-01-11', v => v.model_id = 'B', v => v.training_version = 'v3',
    v => v.result_type = 'experimental_inference', v => v.information_cutoff = '2024-01-06',
    v => v.origin_week_start = '2024-01-07', v => v.radio_ids = ['000002'],
    v => v.result.origin_week_start = '2024-01-07', v => v.result.target_week_start = '2024-01-14']) {
    const bad = structuredClone(value); change(bad)
    assert.throws(() => validateDateQuery(bad, temporal.requested_date, models[0], ['000001'], temporal))
  }
  const unavailable = { ...value, availability: 'unavailable', result_type: 'unavailable', result: null, blockers: ['temporal_provenance_not_verified'] }
  validateDateQuery(unavailable, temporal.requested_date, models[0], ['000001'], temporal)
  assert.throws(() => validateDateQuery({ ...unavailable, result: collection() }, temporal.requested_date, models[0], ['000001'], temporal))
  assert.throws(() => validateDateQuery({ ...unavailable, blockers: ['invented'] }, temporal.requested_date, models[0], ['000001'], temporal))
})

test('map rejects another model/week and distinguishes errors from missing scores', () => {
  const geometry = { features: [{ properties: { radio_id: '000001' }, geometry: null }] }
  const current = { A: { value: collection('A') }, B: { value: { ...collection('B'), target_week_start: '2024-01-14' } } }
  assert.equal(joinComparisonGeometry(geometry, current, '2024-01-07', 'difference').features[0].properties.difference, null)
  current.B = { error: 'disconnected' }
  assert.equal(joinComparisonGeometry(geometry, current, '2024-01-07', 'B').features[0].properties.score_status, 'error')
  assert.equal(joinComparisonGeometry(geometry, current, '2024-01-07', 'A').features[0].properties.score_status, 'available')
  current.B = { unavailable: 'no_frozen_prediction' }
  assert.equal(joinComparisonGeometry(geometry, current, '2024-01-07', 'B').features[0].properties.score_status, 'not_computed')
})

test('new A inference is separately validated and mapped while B remains unavailable', () => {
  const temporal = { schema_version: 'sigard-private-spatial-date-query/1', requested_date: '2026-11-04',
    calendar_version: 'ar-snvs-2020-2026-v1', calendar_min: '2019-12-29', calendar_max: '2027-01-02', calendar_status: 'supported',
    horizon_weeks: 1, information_cutoff: null, operational_use_authorized: false, publication_authorized: false,
    target_week_start: '2026-11-01', target_week_end: '2026-11-07', target_epidemiological_year: 2026, target_epidemiological_week: 44,
    origin_week_start: '2026-10-25', origin_week_end: '2026-10-31', calendar_cutoff: '2026-10-31' }
  const cutoff = '2026-10-28T01:00:00+00:00'
  const result = { ...collection('A', .42), ...temporal, ...models[0], schema_version: 'sigard-experimental-spatial-inference/1',
    information_cutoff: cutoff, data_kind: 'private_experimental_inference', prediction_target: 'binary_experimental_record_presence_next_week',
    retrospective: false, provenance: { source_snapshot_id: 'ab-fixed-context-fictional', context_available_at: '2026-10-27T18:00:00+00:00',
      model_available_at: '2026-10-27T18:00:00+00:00', availability_basis: 'local_hash_verified_observation_now',
      historical_availability_accredited: false, model_fitted: false, context_semantics: 'fixed_2022_census_context_not_current_population' } }
  result.rows[0].data_availability = { prediction_as_of: cutoff, epidemiological_history: 'not_used_by_model', known_lag_count: null, operational_availability: 'not_accredited' }
  const value = { ...temporal, ...models[0], territory_version: 'capital-census-2022-public-v1', radio_ids: ['000001'],
    information_cutoff: cutoff, new_inference_enabled: true, availability: 'available', result_type: 'experimental_inference', result, blockers: [] }
  validateDateQuery(value, temporal.requested_date, models[0], ['000001'], temporal)
  for (const mutate of [v => v.result.target_week_start = '2026-11-08', v => v.result.training_version = 'V3',
    v => v.result.provenance.context_available_at = '2026-11-02T00:00:00Z', v => v.result.provenance.model_fitted = true,
    v => v.information_cutoff = '2026-11-01T04:00:00Z', v => v.result.retrospective = true,
    v => v.result.rows[0].experimental_score = null, v => v.new_inference_enabled = false]) {
    const bad = structuredClone(value); mutate(bad)
    assert.throws(() => validateDateQuery(bad, temporal.requested_date, models[0], ['000001'], temporal))
  }
  const geometry = { features: [{ properties: { radio_id: '000001' }, geometry: null }] }
  const current = { A: { value: result, query: value }, B: { unavailable: 'recent_epidemiological_history_unavailable' } }
  const mapped = joinComparisonGeometry(geometry, current, temporal.target_week_start, 'A').features[0].properties
  assert.equal(mapped.experimental_score, .42)
  assert.equal(mapped.result_type, 'experimental_inference')
  assert.equal(mapped.difference, null)
})
