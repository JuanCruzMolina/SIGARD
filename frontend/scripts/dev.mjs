import { spawn } from 'node:child_process'
import { access } from 'node:fs/promises'
import { createServer } from 'node:net'
import { dirname, join, delimiter } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { validateCatalog } from '../src/services/experimentalContract.mjs'

const frontend = dirname(dirname(fileURLToPath(import.meta.url)))
const repository = dirname(frontend)
const origin = 'http://127.0.0.1:5173'
const api = 'http://127.0.0.1:8765'
const python = join(repository, 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')

export async function portAvailable(port) {
  const server = createServer()
  return new Promise((resolve, reject) => {
    server.once('error', error => error.code === 'EADDRINUSE' ? resolve(false) : reject(error))
    server.listen({ host: '127.0.0.1', port, exclusive: true }, () => server.close(() => resolve(true)))
  })
}

// A generic /health is insufficient: check the existing contract and local guard.
// Never print response bodies, follow redirects, or send credentials.
export async function identifyApi(base = api) {
  const request = (path, headers = {}) => fetch(`${base}${path}`, {
    headers, redirect: 'error', credentials: 'omit', cache: 'no-store', signal: AbortSignal.timeout(3000),
  })
  try {
    const health = await request('/health')
    if (!health.ok || (await health.json()).status !== 'ok') return false
    const catalog = await request('/api/v1/research/spatial/models', {
      Origin: origin, 'X-Sigard-Research': 'local-read',
    })
    if (!catalog.ok || catalog.headers.get('access-control-allow-origin') !== origin
      || catalog.headers.get('cache-control') !== 'no-store, private') return false
    validateCatalog(await catalog.json())
    const denied = await request('/api/v1/research/spatial/models')
    await denied.body?.cancel()
    return denied.status === 403
  } catch {
    return false
  }
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

export const developmentRuntime = {
  portAvailable,
  identifyApi,
  async ensurePython() {
    try { await access(python) } catch {
      throw new Error('Falta el entorno backend/.venv. Crealo e instalá backend/requirements.research.txt; consultá frontend/README.md.')
    }
  },
  startApi: () => spawnOwned(python, ['-B', '-m', 'app.research_local'], {
    cwd: repository,
    env: { ...process.env, PYTHONPATH: [join(repository, 'backend'), process.env.PYTHONPATH].filter(Boolean).join(delimiter) },
  }),
  async createVite() {
    const { createServer: createViteServer } = await import('vite')
    return createViteServer({ root: frontend, configFile: join(frontend, 'vite.config.js') })
  },
  log: message => console.log(`[SIGARD] ${message}`),
}

export async function startDevelopment(runtime = developmentRuntime) {
  let ownedApi, companion, vite, stopping, stopped = false
  const wasRaw = process.stdin.isRaw
  let finish, finishStartup
  const closed = new Promise(resolve => { finish = resolve })
  const startupFinished = new Promise(resolve => { finishStartup = resolve })
  const stop = (code = 0) => {
    stopped = true
    stopping ??= (async () => {
      // Finish any in-flight creation/listen before closing its resources.
      await startupFinished
      const results = await Promise.allSettled([vite?.close(), companion?.stop(), ownedApi?.stop()])
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
    if (!await runtime.portAvailable(8765)) {
      if (!await runtime.identifyApi()) {
        throw new Error('El puerto 127.0.0.1:8765 está ocupado y no responde como la API experimental válida. Revisá ese proceso; SIGARD no lo detendrá.')
      }
      runtime.log('API experimental existente verificada; se reutiliza y seguirá activa al salir.')
    } else {
      await runtime.ensurePython()
      checkStopped()
      runtime.log('Iniciando API experimental en 127.0.0.1:8765…')
      ownedApi = runtime.startApi()
      let apiExit
      ownedApi.exited.then(result => {
        apiExit = result
        if (!stopped) {
          runtime.log('La API experimental terminó. Revisá las dependencias y los artefactos locales; no se regeneran automáticamente.')
          void stop(1)
        }
      })
      const deadline = Date.now() + 30000
      while (!await runtime.identifyApi()) {
        if (apiExit || stopped) throw new Error('La API experimental no pudo iniciarse.')
        if (Date.now() >= deadline) throw new Error('La API experimental no estuvo lista en 30 segundos. Revisá su salida y el puerto 8765.')
        await delay(200)
      }
    }
    checkStopped()
    if (runtime.startCompanion) {
      companion = runtime.startCompanion()
      companion.exited.then(() => {
        if (!stopped) {
          runtime.log('La API de demostración terminó; se cierra la sesión local.')
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
    runtime.log(`Listo: ${origin}/mapa · Ctrl+C cierra únicamente lo iniciado por este comando.`)
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

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv.length > 2) throw new Error('El inicio local usa los hosts y puertos fijos de SIGARD; ejecutá npm.cmd --prefix frontend run dev sin argumentos adicionales.')
    const session = await startDevelopment()
    process.exitCode = await session.closed
  } catch (error) {
    console.error(`[SIGARD] ${error.message}`)
    process.exitCode = 1
  }
}
