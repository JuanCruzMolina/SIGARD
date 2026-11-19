// npm run dev:alerts — internal alerts over the already integrated predictions.
// Ports: 5173 (Vite), 8765 (local predictive API, started or reused, read-only) and
// 8767 (administrative alerts API with a private persistent SQLite in
// data/interim/official/internal-alerts-v1/, ignored by Git). It shares 5173 with
// `dev` and `dev:demo`, so it never runs in parallel with them.
import { mkdir, mkdtemp, rm } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { developmentRuntime, portAvailable, spawnOwned, startDevelopment } from './dev.mjs'
import { demoEnvironment, demoOfflineStyles } from './dev-demo.mjs'

const frontend = dirname(dirname(fileURLToPath(import.meta.url)))
const backend = join(dirname(frontend), 'backend')
const python = join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
export const ALERTS_API = 'http://127.0.0.1:8767'
export const CREATE_ADMIN = '.\\backend\\.venv\\Scripts\\python.exe -B backend/app/alerts_local.py create-admin'

// mode 'serve': persistent private store; mode 'session': disposable SQLite + generated admin (checks only).
export function createAlertsService({ mode = 'serve', source = 'local-research' } = {}) {
  let child, directory, credentials, stopping, childExited = false
  const ready = (async () => {
    const args = ['-I', '-B', join(backend, 'app/alerts_local.py')]
    if (mode === 'session') {
      await mkdir(join(backend, '.tmp'), { recursive: true })
      directory = await mkdtemp(join(backend, '.tmp', 'sigard-alerts-'))
      args.push('session', '--directory', directory, '--source', source)
    } else args.push('serve')
    child = spawnOwned(python, args, { cwd: directory || dirname(frontend), env: demoEnvironment(), input: true, silent: true })
    child.exited.then(() => { childExited = true })
    child.stderr.resume()
    child.stdin.on('error', () => {})
    const first = await Promise.race([
      new Promise((resolve, reject) => {
        let buffer = ''
        child.stdout.on('data', data => {
          buffer += data.toString()
          if (buffer.length > 4096) return reject(new Error('Respuesta inválida de la API de alertas.'))
          if (buffer.includes('\n')) { try { resolve(JSON.parse(buffer.split('\n')[0])) } catch { reject(new Error('Respuesta inválida de la API de alertas.')) } }
        })
      }),
      child.exited.then(() => { throw new Error('La API de alertas terminó antes de estar lista. Revisá las dependencias backend y el puerto 8767.') }),
      delay(30000, null, { ref: false }).then(() => { throw new Error('La API de alertas no inició en 30 segundos.') }),
    ])
    if (first.error === 'no_admin') throw new Error(`No hay cuenta de administrador en el almacenamiento privado de alertas. Creala una vez con: ${CREATE_ADMIN}`)
    const deadline = Date.now() + 15000
    while (true) {
      if (childExited) throw new Error('La API de alertas terminó durante la inicialización.')
      try {
        const health = await (await fetch(`${ALERTS_API}/health/alerts`, { redirect: 'error', signal: AbortSignal.timeout(1000) })).json()
        if (health.alerts === true && health.session === first.session) break
      } catch { /* Await only the child identified by its random nonce. */ }
      if (Date.now() >= deadline) throw new Error('La API de alertas no estuvo lista; revisá el puerto 8767.')
      await delay(100)
    }
    if (mode === 'session') credentials = { email: first.email, password: first.password }
  })()
  const exited = ready.then(() => child.exited, () => ({ error: true }))
  return {
    ready, exited,
    get credentials() { return credentials },
    get directory() { return directory },
    stop() {
      stopping ??= (async () => {
        if (child) {
          child.stdin.end('stop\n')
          const graceful = await Promise.race([child.exited.then(() => true), delay(5000, false, { ref: false })])
          if (!graceful) await child.stop()
          await child.exited
        }
        credentials = undefined
        // Only the exact disposable directory created above; never the persistent store.
        if (directory) await rm(directory, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 })
      })()
      return stopping
    },
  }
}

export function alertsRuntime(options = {}) {
  let service
  return {
    ...developmentRuntime,
    research: options.source !== 'fictional',
    async checkRequirements() {
      if (!await portAvailable(8767)) throw new Error('El puerto 127.0.0.1:8767 está ocupado. dev:alerts no reutiliza ni detiene ese servicio.')
      await developmentRuntime.ensurePython()
    },
    startCompanion() { service = createAlertsService(options); return service },
    async createVite() {
      const { createServer } = await import('vite')
      // No external fonts: the alerts panel works offline like the demo.
      return createServer({ root: frontend, configFile: join(frontend, 'vite.config.js'), plugins: [demoOfflineStyles()],
        define: { 'import.meta.env.VITE_API_URL': JSON.stringify(ALERTS_API) } })
    },
    announce() {
      developmentRuntime.log('ALERTAS INTERNAS: /admin/reportes → «Alertas internas». Avisos sólo en el panel; sin correo, SMS ni publicación ciudadana.')
      developmentRuntime.log('Puertos: 5173 frontend · 8765 API predictiva (sólo lectura) · 8767 API de alertas. No correr en paralelo con dev ni dev:demo.')
    },
    get service() { return service },
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv.length > 2) throw new Error('Ejecutá npm run dev:alerts sin argumentos; hosts y puertos son fijos.')
    const session = await startDevelopment(alertsRuntime())
    process.exitCode = await session.closed
  } catch (error) {
    console.error(`[SIGARD] ${error.message}`)
    process.exitCode = 1
  }
}
