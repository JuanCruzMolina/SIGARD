// Private outputs of the browser and performance harnesses (below data/interim/official, ignored
// by Git). Rule: a run never deletes, empties or overwrites anything there. Each run writes into a
// NEW folder named by its label (SIGARD_SHOTS_LABEL, or --label for performance); when no label is
// given, a timestamped one is used. An existing folder stops the run before it writes anything.
import { mkdir, stat } from 'node:fs/promises'
import { resolve } from 'node:path'

export const LABEL_PATTERN = /^[a-z0-9][a-z0-9-]{0,59}$/

export function runLabel(label = process.env.SIGARD_SHOTS_LABEL, now = new Date()) {
  const value = label || `run-${now.toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-')}`
  if (!LABEL_PATTERN.test(value)) throw new Error(`Etiqueta inválida «${value}»: minúsculas, dígitos y guiones.`)
  return value
}

export async function exists(path) {
  return stat(path).then(() => true, error => { if (error.code === 'ENOENT') return false; throw error })
}

// Creates <base>/<label>/<...parts> only when <base>/<label> does not exist yet.
export async function newRunDirectory(base, label, ...parts) {
  const run = resolve(base, label)
  if (await exists(run)) throw new Error(`${run} ya existe: usá otra etiqueta. Los arneses nunca sobrescriben ni vacían resultados privados.`)
  const directory = resolve(run, ...parts)
  await mkdir(directory, { recursive: true })
  return directory
}
