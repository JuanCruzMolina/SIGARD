// Harness outputs below data/: a new folder per run label, never emptied, deleted or overwritten.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readdir, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'
import { DIAG_ROOT, newRunDirectory, outputBase, runLabel } from './private-output.mjs'

test('labels: explicit or timestamped, lowercase digits and hyphens only', () => {
  assert.equal(runLabel('f4-regresion'), 'f4-regresion')
  assert.equal(runLabel(undefined, new Date('2026-11-23T22:05:09Z')), 'run-20261123-220509')
  assert.equal(runLabel('', new Date('2026-11-23T22:05:09Z')), 'run-20261123-220509')
  for (const bad of ['../data', 'F4', 'a/b', '-x', 'con espacio']) assert.throws(() => runLabel(bad), /Etiqueta inválida/)
})

test('a run folder is created only when new; an existing one stops the run and stays untouched', async () => {
  const base = await mkdtemp(join(tmpdir(), 'sigard-private-output-'))
  const first = await newRunDirectory(base, 'antes', 'real', 'sin-conexion')
  assert.equal(first, join(base, 'antes', 'real', 'sin-conexion'))
  await writeFile(join(first, 'captura.private.png'), 'previa')
  await assert.rejects(newRunDirectory(base, 'antes', 'fictional'), /ya existe: usá otra etiqueta/)
  assert.equal(await readFile(join(first, 'captura.private.png'), 'utf8'), 'previa')
  assert.deepEqual(await readdir(join(base, 'antes')), ['real'])
  assert.ok(await newRunDirectory(base, 'despues'))
})

test('every harness writing below data/interim/official uses a new run folder and never empties or deletes', async () => {
  for (const file of ['performance', 'predictive', 'alerts', 'public-activity', 'backtest', 'admin-shell']) {
    const source = await readFile(new URL(`./${file}.browser.mjs`, import.meta.url), 'utf8')
    assert.match(source, /newRunDirectory\(/, file)
    assert.doesNotMatch(source, /emptyOutDir: true|\brmSync\b|\brm\(|rmdir|unlink|recursive: true, force/, file)
    assert.doesNotMatch(source, /mkdir\(output/, file)
  }
  const performance = await readFile(new URL('./performance.browser.mjs', import.meta.url), 'utf8')
  assert.match(performance, /emptyOutDir: false/)
  assert.doesNotMatch(performance, /results-\$\{label\}/, 'results go inside the run folder')
})

test('SIGARD_DIAG_PHASE sends trial runs to frontend/.tmp/diag/<phase>/, never below data/', () => {
  const base = resolve('C:/x/data/interim/official/ux-admin-v2-f6-5')
  assert.equal(outputBase(base, undefined), base, 'without a phase: the evidence folder')
  assert.equal(outputBase(base, 'f6-5'), resolve(DIAG_ROOT, 'f6-5', 'ux-admin-v2-f6-5'))
  assert.ok(!outputBase(base, 'f6-5').includes(`${sep}data${sep}`))
  assert.throws(() => outputBase(base, '../fuera'), /Fase de diagnóstico inválida/)
})
