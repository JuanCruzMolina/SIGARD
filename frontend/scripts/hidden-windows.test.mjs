// Static check: processes launched by the project's dev/test scripts never open a visible window
// on Windows. Node: every child_process spawn/exec/execFile/fork (sync or not) passes
// `windowsHide: true`, no `shell: true` and no unconditional `detached: true` (on Windows that is
// DETACHED_PROCESS, which voids the hidden console: the venv launcher's Python then opened a window). Python: every subprocess.run/Popen/call/check_call/
// check_output passes `creationflags=` (the shared NO_WINDOW flag). Comments are ignored.
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)))
const files = (dir, ext) => readdirSync(join(root, dir)).filter(name => name.endsWith(ext)).map(name => join(root, dir, name))
const SELF = fileURLToPath(import.meta.url)
const NODE_FILES = [...files('frontend/scripts', '.mjs'), ...files('tools', '.mjs')].filter(file => resolve(file) !== resolve(SELF))
// Python that runs in tests, tools or the local development API (ML pipelines are offline and out of scope).
const PYTHON_FILES = [...files('backend/tests', '.py'), ...files('tools', '.py'), join(root, 'backend/app/alerts_local.py'), join(root, 'backend/app/experimental_inference.py')]

// Text of each call `name(...)`, with balanced parentheses (strings and templates are skipped).
export function calls(source, pattern) {
  const found = []
  for (const match of source.matchAll(pattern)) {
    let depth = 0, end = match.index + match[0].length - 1, quote = null
    for (let i = end; i < source.length; i++) {
      const c = source[i]
      if (quote) { if (c === '\\') i++; else if (c === quote) quote = null; continue }
      if (c === '"' || c === "'" || c === '`') quote = c
      else if (c === '(') depth++
      else if (c === ')' && --depth === 0) { end = i; break }
    }
    found.push({ line: source.slice(0, match.index).split('\n').length, text: source.slice(match.index, end + 1) })
  }
  return found
}
const stripComments = (source, python) => python
  ? source.replace(/^\s*#.*$/gm, '')
  : source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:\\])\/\/.*$/gm, '$1')

const NODE_CALL = /(?<![.\w])(?:spawn|spawnSync|exec|execSync|execFile|execFileSync|fork)\s*\(/g
const PYTHON_CALL = /\bsubprocess\.(?:run|Popen|call|check_call|check_output)\s*\(/g

test('child_process calls in frontend/scripts and tools hide their window', () => {
  const missing = []
  for (const file of NODE_FILES) {
    const source = readFileSync(file, 'utf8')
    if (!/child_process/.test(source)) continue
    for (const call of calls(stripComments(source, false), NODE_CALL)) {
      if (!/windowsHide\s*:\s*true/.test(call.text) || /shell\s*:\s*true/.test(call.text) || /detached\s*:\s*true/.test(call.text)) missing.push(`${relative(root, file)}:${call.line}`)
    }
  }
  assert.deepEqual(missing, [], `sin windowsHide: true (o con shell: true o detached: true): ${missing.join(', ')}`)
})

test('subprocess calls in backend tests, tools and the local API hide their window', () => {
  const missing = []
  for (const file of PYTHON_FILES) {
    const source = readFileSync(file, 'utf8')
    for (const call of calls(stripComments(source, true), PYTHON_CALL)) {
      if (!/creationflags\s*=/.test(call.text)) missing.push(`${relative(root, file)}:${call.line}`)
    }
  }
  assert.deepEqual(missing, [], `sin creationflags (CREATE_NO_WINDOW): ${missing.join(', ')}`)
})

test('the check itself finds calls with and without the option', () => {
  assert.equal(calls("spawn('a', ['b'], { windowsHide: true, x: f(1) })", NODE_CALL)[0].text, "spawn('a', ['b'], { windowsHide: true, x: f(1) })")
  assert.equal(calls("x = /re(/.exec(s); spawnSync(node, [')'])", NODE_CALL).length, 1)
  assert.equal(calls('subprocess.run(["git", "x"], cwd=root)', PYTHON_CALL)[0].text, 'subprocess.run(["git", "x"], cwd=root)')
})
