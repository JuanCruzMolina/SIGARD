import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const frontend = fileURLToPath(new URL('../', import.meta.url))
const read = path => readFileSync(resolve(frontend, path), 'utf8')

test('exact-values mode is gated by DEV and the explicit private-view define only', () => {
  assert.match(read('src/services/privateView.js'), /import\.meta\.env\.DEV && import\.meta\.env\.SIGARD_PRIVATE_VIEW === true/)
  const viewer = read('src/components/HistoricalBacktest.jsx')
  const selector = viewer.indexOf('id="bt-disclosure"')
  assert.ok(selector > 0)
  assert.ok(viewer.lastIndexOf('privateViewEnabled ?', selector) > viewer.lastIndexOf('</details>', selector), 'selector must be inside the privateViewEnabled branch')
  assert.equal((viewer.match(/value="private"/g) || []).length, 1)
  assert.match(viewer, /useState\('presentation'\)/)
  // Only the dev coordinator defines the flag; vite.config.js (used by builds) never does.
  assert.doesNotMatch(read('vite.config.js'), /SIGARD_PRIVATE_VIEW/)
  assert.match(read('scripts/dev.mjs'), /SIGARD_PRIVATE_VIEW': JSON\.stringify\(privateViewRequested\(\)\)/)
})

test('production bundle contains no exact-values option', { skip: !existsSync(resolve(frontend, 'dist/assets')) && 'run the build first' }, () => {
  const bundles = readdirSync(resolve(frontend, 'dist/assets')).filter(name => name.endsWith('.js'))
  assert.ok(bundles.length > 0)
  for (const name of bundles) {
    const text = readFileSync(resolve(frontend, 'dist/assets', name), 'utf8')
    assert.ok(!text.includes('Investigación privada · valores exactos'), `exact-values option bundled in ${name}`)
  }
})
