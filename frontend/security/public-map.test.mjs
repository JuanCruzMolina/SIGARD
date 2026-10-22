import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { transformWithOxc } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// Render the real component; only the browser-only Leaflet surface is replaced.
// Fixtures are fictional. Browser interaction is checked separately with the dev app.
const url = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const reactUrl = new URL('../node_modules/react/index.js', import.meta.url).href
const dataSource = await readFile(new URL('../src/services/sigardData.js', import.meta.url), 'utf8')
const replacements = {
  react: reactUrl,
  'react/jsx-runtime': new URL('../node_modules/react/jsx-runtime.js', import.meta.url).href,
  'react-leaflet': url(`import React from ${JSON.stringify(reactUrl)};
    export const MapContainer=({children})=>React.createElement('div',{},children);
    export const GeoJSON=({data,interactive=true})=>React.createElement('div',{'data-layer-count':data.features?.length || 1,'data-interactive':String(interactive)});
    export const useMap=()=>({fitBounds(){},setView(){}});`),
  leaflet: url("export default {geoJSON(data){return {getBounds(){return {isValid(){return Boolean(data?.features?.length || data?.type==='Feature')}}}}}}"),
  'leaflet/dist/leaflet.css': url(''),
  '../services/sigardData': url(dataSource.replace('import.meta.env.VITE_API_URL', 'undefined').replace("import { demoMode } from './demoMode'", 'const demoMode = false')),
  '../services/experimentalContract.mjs': new URL('../src/services/experimentalContract.mjs', import.meta.url).href,
}
const source = await readFile(new URL('../src/components/SigardComponents.jsx', import.meta.url), 'utf8')
const transformed = await transformWithOxc(source, 'SigardComponents.jsx', { jsx: { runtime: 'automatic' } })
const code = transformed.code.replace(/(['"])([^'"]+)\1/g, (original, quote, value) => replacements[value] ? JSON.stringify(replacements[value]) : original)
const { TerritorialMap } = await import(url(code))

function collection(score = .123456) {
  return { type: 'FeatureCollection', features: Array.from({ length: 263 }, (_, i) => ({
    type: 'Feature', geometry: { type: 'Polygon', coordinates: [] },
    properties: { radio_id: String(i + 1).padStart(9, '0'), population: 123, households: 45, dwellings: 50,
      population_density: 10, area_km2: 12.3, percentile: 50, relative_level: 'medium',
      experimental_spatial_score: score, synthetic_scenario: 'spatial_clusters',
      target_week_start: '2024-06-23', target_week_end: '2024-06-29' },
  })).reverse() }
}
const render = props => renderToStaticMarkup(React.createElement(TerritorialMap, {
  geojson: collection(), view: 'context', disclaimer: 'Simulación: no representa casos observados.', ...props,
}))

test('public selector exposes all 263 textual codes in order with an associated label and live detail', () => {
  const html = render()
  assert.equal((html.match(/<option /g) || []).length, 264)
  assert.ok(html.indexOf('value="000000001"') < html.indexOf('value="000000263"'))
  const selectId = html.match(/<select id="([^"]+)"/)[1]
  assert.ok(html.includes(`for="${selectId}"`))
  const detailId = html.match(/aria-controls="([^"]+)"/)[1]
  assert.ok(html.includes(`id="${detailId}" aria-live="polite" aria-atomic="true"`))
  assert.ok(html.includes('263 radios disponibles') && html.includes('con el teclado'))
  assert.ok(html.includes('data-layer-count="263"'))
})

test('empty selection explains how to consult the aggregate detail without inventing values', () => {
  const html = render()
  assert.ok(html.includes('Elegí un código en el selector'))
  assert.ok(!html.includes('Densidad poblacional') && !html.includes('radio-details'))
})

test('selected code resolves against the current layer and week, keeping synthetic labels', () => {
  const selectedRadio = '000000001'
  const context = render({ selectedRadio })
  assert.ok(context.includes(`value="${selectedRadio}" selected=""`))
  assert.ok(context.includes('Densidad poblacional') && context.includes('123'))
  const simulation = render({ selectedRadio, view: 'simulation' })
  assert.ok(simulation.includes('Índice espacial experimental') && simulation.includes('0,123456'))
  assert.ok(simulation.includes('Escenario espacial agrupado') && simulation.includes('no representa casos observados'))
  const next = collection(.654321)
  next.features.forEach(f => { f.properties.target_week_start = '2024-06-30'; f.properties.target_week_end = '2024-07-06' })
  const changed = render({ selectedRadio, view: 'simulation', geojson: next })
  assert.ok(changed.includes('0,654321') && changed.includes('30/06/2024'))
  assert.ok(!changed.includes('0,123456') && !changed.includes('23/06/2024'))
  assert.ok(changed.includes('data-interactive="false"'))
})

test('compact preview and research keep their existing controls without a public selector', () => {
  for (const props of [{ compact: true }, { view: 'research' }]) {
    const html = render(props)
    assert.ok(!html.includes('Consultar un radio censal') && !html.includes('<select'))
    assert.ok(html.includes('data-layer-count="263"'))
  }
})

test('loading hides stale details and disables selection; missing geometry reports an error', () => {
  const loading = render({ selectedRadio: '000000001', showData: false, statusMessage: 'Cargando capa pública…' })
  assert.ok(loading.includes('disabled=""') && loading.includes('Cargando capa pública…'))
  assert.ok(!loading.includes('Densidad poblacional') && !loading.includes('data-layer-count'))
  const error = render({ geojson: { type: 'FeatureCollection', features: [] } })
  assert.ok(error.includes('role="alert"') && error.includes('No fue posible cargar'))
  assert.ok(!error.includes('<select'))
})
