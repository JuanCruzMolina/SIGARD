// Private outputs of the browser and performance harnesses (below data/interim/official, ignored
// by Git). Rule: a run never deletes, empties or overwrites anything there. Each run writes into a
// NEW folder named by its label (SIGARD_SHOTS_LABEL, or --label for performance); when no label is
// given, a timestamped one is used. An existing folder stops the run before it writes anything.
import { mkdir, stat } from 'node:fs/promises'
import { basename, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const LABEL_PATTERN = /^[a-z0-9][a-z0-9-]{0,59}$/

export function runLabel(label = process.env.SIGARD_SHOTS_LABEL, now = new Date()) {
  const value = label || `run-${now.toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-')}`
  if (!LABEL_PATTERN.test(value)) throw new Error(`Etiqueta inválida «${value}»: minúsculas, dígitos y guiones.`)
  return value
}

export async function exists(path) {
  return stat(path).then(() => true, error => { if (error.code === 'ENOENT') return false; throw error })
}

// Diagnostic, trial and repeat runs (not a phase's final evidence) stay out of data/: with
// SIGARD_DIAG_PHASE=<phase> the run goes to frontend/.tmp/diag/<phase>/<base folder>/ (ignored by Git).
export const DIAG_ROOT = fileURLToPath(new URL('../.tmp/diag/', import.meta.url))
export function outputBase(base, phase = process.env.SIGARD_DIAG_PHASE) {
  if (!phase) return base
  if (!LABEL_PATTERN.test(phase)) throw new Error(`Fase de diagnóstico inválida «${phase}»: minúsculas, dígitos y guiones.`)
  return resolve(DIAG_ROOT, phase, basename(base))
}

// Creates <base>/<label>/<...parts> only when <base>/<label> does not exist yet.
export async function newRunDirectory(base, label, ...parts) {
  const run = resolve(outputBase(base), label)
  if (await exists(run)) throw new Error(`${run} ya existe: usá otra etiqueta. Los arneses nunca sobrescriben ni vacían resultados privados.`)
  const directory = resolve(run, ...parts)
  await mkdir(directory, { recursive: true })
  return directory
}
