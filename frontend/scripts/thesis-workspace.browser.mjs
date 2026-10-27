// Called only by the real, disposable demo browser test. No response mocks.
import assert from 'node:assert/strict'
import { performance } from 'node:perf_hooks'
import { cpus, totalmem, release } from 'node:os'
import { resolve } from 'node:path'

export const measurements = []
export async function measure(operation, action) {
  const start = performance.now()
  await action()
  const milliseconds = Number((performance.now() - start).toFixed(2))
  measurements.push({ operation, milliseconds })
  assert.ok(milliseconds < 5000, `${operation} took ${milliseconds} ms; requirement <5000 ms`)
}
export async function conditions(browser) {
  return { os: `${process.platform} ${release()}`, cpu: cpus()[0].model, logical_cpus: cpus().length,
    ram_gib: Number((totalmem() / 1024 ** 3).toFixed(1)), node: process.version, browser: await browser.version(),
    headless: true, viewport: '1440x1000; responsive check 390x1000', network: 'loopback only; external requests blocked',
    cpu_throttling: false, network_throttling: false, cache: 'new browser for first map; warm application for subsequent actions',
    sample: 'one functional run, not a load/concurrency test', requirement_ms: 5000 }
}

export async function exerciseWorkspace({ page, fill, clickText, checkpoint, output }) {
  const ready = () => page.waitForFunction(() => document.querySelector('.demo-query-result')?.dataset.queryState === 'available')
  const query = (field, value) => page.waitForFunction((field, value) => {
    const node = document.querySelector('.demo-query-result')
    return node?.dataset.queryState === 'available' && JSON.parse(node.dataset.queryKey)[field] === value
  }, {}, field, value)
  await measure('admin_workspace_load', async () => {
    await clickText('Análisis y alertas demo'); await ready()
    await page.waitForSelector('.demo-workspace .leaflet-overlay-pane path')
  })
  assert.equal(await page.$eval('#demo-method', node => node.value), 'persistence')
  assert.equal(await page.$$eval('.demo-workspace .public-radio-control option', nodes => nodes.length), 7)
  for (const horizon of ['2', '4', '1']) await measure('query_horizon_change', async () => {
    await page.select('#demo-horizon', horizon); await query('horizon', horizon)
  })
  for (const radio of ['D01', 'D05', 'D06']) await measure('query_radio_change', async () => {
    await page.select('.demo-workspace .public-radio-control select', radio); await query('radio', radio)
    await page.waitForSelector('.demo-estimate')
  })
  assert.equal(await page.$eval('.demo-estimate', node => node.textContent), 'Sin estimación')
  await page.select('#demo-method', 'v3_experimental'); await query('method', 'v3_experimental')
  assert.match(await page.$eval('.demo-query-result', node => node.textContent), /fixture-v3_experimental/)
  await measure('query_unavailable_2026', async () => {
    await page.$eval('#demo-date', node => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(node, '2026-10-26')
      node.dispatchEvent(new Event('input', { bubbles: true }))
      node.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await page.waitForFunction(() => document.querySelector('.demo-query-result')?.dataset.queryState === 'insufficient_data')
  })
  assert.equal(await page.$('.demo-estimate'), null)
  await page.select('#demo-week', '2024-04-07'); await ready()
  await page.select('#demo-method', 'persistence'); await query('method', 'persistence')
  await page.select('.demo-workspace .public-radio-control select', 'D01'); await query('radio', 'D01')
  await clickText('Restablecer vista')
  checkpoint('Fictional prediction contract: date/radio/horizons, persistence default, illustrative V3, nulls and no invented 2026 results')
  for (const width of [1440, 390]) {
    await page.setViewport({ width, height: 1000 })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Overflow at ${width}`)
    if (width === 390) assert.ok(await page.evaluate(() => {
      const legend = document.querySelector('.demo-workspace .count-legend').getBoundingClientRect()
      const detail = document.querySelector('.demo-workspace .map-side-panel').getBoundingClientRect()
      return legend.bottom <= detail.top + 1
    }), 'Count legend must not overlap the mobile selector/detail')
    await page.screenshot({ path: resolve(output, `fictional-analysis-${width}.png`), fullPage: true })
  }
  await page.setViewport({ width: 1440, height: 1000 })
  await page.setOfflineMode(true); await page.select('#demo-horizon', '2')
  await page.waitForSelector('.demo-query-result [role=alert]')
  assert.equal(await page.$('.demo-estimate'), null)
  await page.setOfflineMode(false); await page.select('#demo-horizon', '1'); await ready()
  checkpoint('Failed query hides stale estimates and recovers after connection returns')

  await clickText('Ingestión ficticia')
  await fill('#demo-csv', 'week_start,radio_id,count,person\n2024-04-07,D01,1,forbidden')
  await clickText('Validar y cargar fixture'); await page.waitForSelector('.demo-workspace [role=alert]')
  assert.equal(await page.$('.demo-import-result'), null)
  await clickText('Restaurar ejemplo')
  await page.$eval('#demo-csv', node => {
    const changed = node.value.replace('2024-03-24,D01,3', '2024-03-24,D01,9')
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(node, changed)
    node.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await measure('fixture_ingestion', async () => {
    await clickText('Validar y cargar fixture'); await page.waitForSelector('.demo-import-result')
  })
  assert.match(await page.$eval('.demo-import-result', node => node.textContent), /48 filas, 36 conocidas y 12 desconocidas/)
  assert.ok((await page.$eval('#demo-csv', node => node.value)).includes('2024-03-24,D01,9'))
  await clickText('Consulta territorial'); await ready()
  await page.waitForFunction(() => document.querySelector('.demo-estimate')?.textContent === '9')
  checkpoint('CSV ingestion rejects extra fields and loads 48 fictitious rows with 12 explicit unknowns')

  await clickText('Alertas experimentales')
  await fill('.demo-rule-form input[type=number]', '0')
  await clickText('Crear regla'); await page.waitForSelector('.demo-rule-list li')
  await measure('experimental_alert_evaluation', async () => {
    await clickText('Evaluar candidatas para la fecha y horizonte'); await page.waitForSelector('.demo-candidates li')
  })
  assert.equal(await page.$$eval('.demo-candidates li', nodes => nodes.length), 5)
  await clickText('Marcar revisada (demo)')
  await page.waitForFunction(() => document.querySelector('.demo-candidates')?.textContent.includes('Revisada en demo'))
  await page.reload({ waitUntil: 'networkidle0' }); await page.waitForSelector('.admin-header')
  await clickText('Análisis y alertas demo'); await ready(); await clickText('Alertas experimentales')
  await page.waitForFunction(() => document.querySelector('.demo-candidates')?.textContent.includes('Revisada en demo'))
  await clickText('Editar'); await page.click('.demo-rule-form input[type=checkbox]'); await clickText('Guardar regla')
  await page.waitForFunction(() => document.querySelector('.demo-rule-list')?.textContent.includes('Deshabilitada'))
  await clickText('Evaluar candidatas para la fecha y horizonte')
  await page.waitForFunction(() => !document.querySelector('.demo-candidates li'))
  assert.equal(await page.evaluate(() => localStorage.length), 0)
  checkpoint('Alert configuration, evaluation, review and audit persist through reload; disabling clears candidates; no localStorage or notifications')
  for (const width of [1440, 390]) {
    await page.setViewport({ width, height: 1000 })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
    await page.screenshot({ path: resolve(output, `fictional-alerts-${width}.png`), fullPage: true })
  }
  await page.setViewport({ width: 1440, height: 1000 })
  await clickText('Volver a reportes')
}
