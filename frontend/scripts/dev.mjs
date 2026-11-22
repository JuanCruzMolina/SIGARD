import { spawn } from 'node:child_process'
import { access } from 'node:fs/promises'
import { createServer } from 'node:net'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'

const frontend = dirname(dirname(fileURLToPath(import.meta.url)))
const repository = dirname(frontend)
const origin = 'http://127.0.0.1:5173'
const python = join(repository, 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')

export async function portAvailable(port) {
  const server = createServer()
  return new Promise((resolve, reject) => {
    server.once('error', error => error.code === 'EADDRINUSE' ? resolve(false) : reject(error))
    server.listen({ host: '127.0.0.1', port, exclusive: true }, () => server.close(() => resolve(true)))
  })
}

export function spawnOwned(command, args, options = {}) {
  const { input = false, silent = false, ...spawnOptions } = options
  // Separate process group/console: Ctrl+C is handled by the coordinator, so
  // Windows' venv launcher and its Python child can be stopped together.
  const child = spawn(command, args, {
    ...spawnOptions, detached: true, windowsHide: true, stdio: [input ? 'pipe' : 'ignore', 'pipe', 'pipe'], shell: false,
  })
  if (!silent) {
    child.stdout.pipe(process.stdout)
    child.stderr.pipe(process.stderr)
  }
  const exited = new Promise(resolve => {
    child.once('error', error => resolve({ error }))
    child.once('exit', (code, signal) => resolve({ code, signal }))
  })
  let stopping
  return {
    exited,
    stdin: child.stdin,
    stdout: child.stdout,
    stderr: child.stderr,
    stop() {
      stopping ??= (async () => {
        if (!child.pid || child.exitCode !== null || child.signalCode !== null) return
        if (process.platform === 'win32') {
          // Only the tree rooted at the child we created; never kill by port/name.
          const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {
            windowsHide: true, stdio: 'ignore', shell: false,
          })
          await new Promise((resolve, reject) => {
            killer.once('error', reject)
            killer.once('exit', resolve)
          })
        } else {
          try { process.kill(-child.pid, 'SIGTERM') } catch (error) {
            if (error.code !== 'ESRCH') throw error
          }
          const force = setTimeout(() => {
            try { process.kill(-child.pid, 'SIGKILL') } catch { /* Already stopped. */ }
          }, 3000)
          await exited
          clearTimeout(force)
        }
        const result = await Promise.race([exited, delay(5000, null, { ref: false })])
        if (!result) throw new Error('No se pudo confirmar el cierre del proceso Python iniciado por SIGARD.')
      })()
      return stopping
    },
  }
}

export function privateViewRequested(env = process.env) {
  return env.SIGARD_PRIVATE_VIEW === '1'
}

export const developmentRuntime = {
  portAvailable,
  async ensurePython() {
    try { await access(python) } catch {
      throw new Error('Falta el entorno backend/.venv. Crealo e instalá backend/requirements.research.txt; consultá frontend/README.md.')
    }
  },
  async createVite() {
    const { createServer: createViteServer } = await import('vite')
    // Exact values in the viewer only with an explicit local opt-in (SIGARD_PRIVATE_VIEW=1).
    return createViteServer({ root: frontend, configFile: join(frontend, 'vite.config.js'),
      define: { 'import.meta.env.SIGARD_PRIVATE_VIEW': JSON.stringify(privateViewRequested()) } })
  },
  log: message => console.log(`[SIGARD] ${message}`),
}

export async function startDevelopment(runtime = developmentRuntime) {
  let companion, vite, stopping, stopped = false
  const wasRaw = process.stdin.isRaw
  let finish, finishStartup
  const closed = new Promise(resolve => { finish = resolve })
  const startupFinished = new Promise(resolve => { finishStartup = resolve })
  const stop = (code = 0) => {
    stopped = true
    stopping ??= (async () => {
      // Finish any in-flight creation/listen before closing its resources.
      await startupFinished
      const results = await Promise.allSettled([vite?.close(), companion?.stop()])
      process.off('SIGINT', interrupt)
      process.off('SIGTERM', interrupt)
      if (process.stdin.isTTY) {
        process.stdin.off('data', keyboardInterrupt)
        process.stdin.setRawMode(Boolean(wasRaw))
        process.stdin.pause()
      }
      if (results.some(result => result.status === 'rejected')) {
        runtime.log('No se pudo completar el cierre de los procesos propios.')
        code = 1
      }
      finish(code)
    })()
    return stopping
  }
  const interrupt = () => { void stop() }
  const keyboardInterrupt = data => { if (data.includes(3)) interrupt() }
  process.on('SIGINT', interrupt)
  process.on('SIGTERM', interrupt)
  // Raw input also handles Ctrl+C delivered as a key by Windows terminals.
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(true)
    process.stdin.on('data', keyboardInterrupt)
    process.stdin.resume()
  }
  const checkStopped = () => { if (stopped) throw new Error('Inicio cancelado.') }
  try {
    if (!await runtime.portAvailable(5173)) {
      throw new Error('El puerto 127.0.0.1:5173 está ocupado. Cerrá el frontend anterior antes de iniciar SIGARD.')
    }
    await runtime.checkRequirements?.()
    checkStopped()
    // F2: there is no separate predictive API (8765) any more. The viewer routes live on the
    // local administrative API started below as companion (8767), behind administrator login.
    if (runtime.research === false) runtime.log('Demo ficticia: no se inicia ni consulta el módulo predictivo privado.')
    if (runtime.startCompanion) {
      companion = runtime.startCompanion()
      companion.exited.then(() => {
        if (!stopped) {
          runtime.log(runtime.companionStopped ?? 'La API de demostración terminó; se cierra la sesión local.')
          void stop(1)
        }
      })
      await companion.ready
      checkStopped()
    }
    vite = await runtime.createVite()
    checkStopped()
    await vite.listen()
    checkStopped()
    vite.printUrls()
    runtime.log(`Listo: ${origin}${runtime.research === false ? '/' : '/admin/predictivo'} · Ctrl+C cierra únicamente lo iniciado por este comando.`)
    runtime.announce?.()
    finishStartup()
    return { stop, closed }
  } catch (error) {
    const cancelled = stopped
    finishStartup()
    await stop(1)
    if (!cancelled) throw error
    return { stop, closed }
  }
}

// Entry point of `npm run dev` and of the deprecated alias `dev:alerts`: frontend and the
// complete administrative API (8767), which also serves the authenticated predictive viewer. dev-alerts.mjs
// builds on this module, so it is imported only after this module finished evaluating
// (no top-level await here: that would deadlock the import cycle).
async function main() {
  try {
    if (process.argv.length > 2) throw new Error('El inicio local usa los hosts y puertos fijos de SIGARD; ejecutá npm.cmd --prefix frontend run dev sin argumentos adicionales.')
    if (process.env.npm_lifecycle_event === 'dev:alerts') developmentRuntime.log('dev:alerts está obsoleto y es un alias de dev; usá npm.cmd --prefix frontend run dev.')
    const { alertsRuntime } = await import('./dev-alerts.mjs')
    const session = await startDevelopment(alertsRuntime())
    process.exitCode = await session.closed
  } catch (error) {
    console.error(`[SIGARD] ${error.message}`)
    process.exitCode = 1
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) void main()
