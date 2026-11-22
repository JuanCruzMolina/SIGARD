// Runtime of `npm run dev` (and of the deprecated alias `dev:alerts`): frontend plus the
// complete local administrative API (login, reports, content, accounts, alerts).
// Ports: 5173 (Vite) and 8767 (administrative API with a private persistent SQLite in
// data/interim/official/internal-alerts-v1/, ignored by Git). Since F2 the same API serves
// the predictive viewer routes (/api/v1/research/predictive, administrator login required)
// and the alerts read them in process; there is no separate predictive API on 8765. It shares 5173 with
// `dev:demo`, so they never run in parallel. The entry point is dev.mjs.
import { mkdir, mkdtemp, rm } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { developmentRuntime, portAvailable, privateViewRequested, spawnOwned } from './dev.mjs'
import { demoEnvironment } from './dev-demo.mjs'

const frontend = dirname(dirname(fileURLToPath(import.meta.url)))
const backend = join(dirname(frontend), 'backend')
const python = join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
export const ALERTS_API = 'http://127.0.0.1:8767'
// The only external origins `dev` opens by itself (src/index.css → IBM Plex Sans).
export const GOOGLE_FONTS = ['fonts.googleapis.com', 'fonts.gstatic.com']
export const CREATE_ADMIN = '.\\backend\\.venv\\Scripts\\python.exe -B backend/app/alerts_local.py create-admin'
export const PREDICTIVE_MISSING = 'El módulo predictivo local no pudo verificarse: el visor responderá 503 hasta revisar los artefactos privados (no se regeneran automáticamente).'
export const ADMIN_MISSING = `No hay cuenta de administrador local: el login de Administración se rechazará hasta crearla. Creala una vez, en otra terminal (la contraseña no se muestra): ${CREATE_ADMIN}`

// mode 'serve': persistent private store; mode 'session': disposable SQLite + generated admin (checks only).
// `launch` exists only so tests can replace the Python process.
export function createAlertsService({ mode = 'serve', source = 'local-research', launch = (args, options) => spawnOwned(python, args, options) } = {}) {
  let child, directory, credentials, stopping, adminMissing = false, predictiveMissing = false, childExited = false
  const ready = (async () => {
    const args = ['-I', '-B', join(backend, 'app/alerts_local.py')]
    if (mode === 'session') {
      await mkdir(join(backend, '.tmp'), { recursive: true })
      directory = await mkdtemp(join(backend, '.tmp', 'sigard-alerts-'))
      args.push('session', '--directory', directory, '--source', source)
    } else args.push('serve')
    child = launch(args, { cwd: directory || dirname(frontend), env: demoEnvironment(), input: true, silent: true })
    child.exited.then(() => { childExited = true })
    child.stderr.resume()
    child.stdin.on('error', () => {})
    const first = await Promise.race([
      new Promise((resolve, reject) => {
        let buffer = ''
        child.stdout.on('data', data => {
          buffer += data.toString()
          if (buffer.length > 4096) return reject(new Error('Respuesta inválida de la API administrativa.'))
          if (buffer.includes('\n')) { try { resolve(JSON.parse(buffer.split('\n')[0])) } catch { reject(new Error('Respuesta inválida de la API administrativa.')) } }
        })
      }),
      child.exited.then(() => { throw new Error('La API administrativa terminó antes de estar lista. Revisá las dependencias backend y el puerto 8767.') }),
      delay(30000, null, { ref: false }).then(() => { throw new Error('La API administrativa no inició en 30 segundos.') }),
    ])
    const deadline = Date.now() + 15000
    while (true) {
      if (childExited) throw new Error('La API administrativa terminó durante la inicialización.')
      try {
        const health = await (await fetch(`${ALERTS_API}/health/alerts`, { redirect: 'error', signal: AbortSignal.timeout(1000) })).json()
        if (health.alerts === true && health.session === first.session) break
      } catch { /* Await only the child identified by its random nonce. */ }
      if (Date.now() >= deadline) throw new Error('La API administrativa no estuvo lista; revisá el puerto 8767.')
      await delay(100)
    }
    adminMissing = mode === 'serve' && first.admin === false
    predictiveMissing = source !== 'fictional' && first.predictive !== true
    if (mode === 'session') credentials = { email: first.email, password: first.password }
  })()
  const exited = ready.then(() => child.exited, () => ({ error: true }))
  return {
    ready, exited,
    get adminMissing() { return adminMissing },
    get predictiveMissing() { return predictiveMissing },
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

export function developmentDefine(env = process.env) {
  return { 'import.meta.env.SIGARD_PRIVATE_VIEW': JSON.stringify(privateViewRequested(env)), 'import.meta.env.VITE_API_URL': JSON.stringify(ALERTS_API) }
}

export function alertsRuntime(options = {}) {
  let service
  return {
    ...developmentRuntime,
    companionStopped: 'La API administrativa (8767) terminó; se cierra la sesión local.',
    async checkRequirements() {
      if (!await portAvailable(8767)) throw new Error('El puerto 127.0.0.1:8767 está ocupado. SIGARD no reutiliza ni detiene ese servicio.')
      await developmentRuntime.ensurePython()
    },
    startCompanion() { service = createAlertsService(options); return service },
    async createVite() {
      const { createServer } = await import('vite')
      // Same styles as `dev` before F1: IBM Plex Sans from Google Fonts (fonts.googleapis.com
      // and fonts.gstatic.com only). Only `dev:demo` strips them (demoOfflineStyles).
      // Exact values in the viewer only with an explicit local opt-in (SIGARD_PRIVATE_VIEW=1).
      return createServer({ root: frontend, configFile: join(frontend, 'vite.config.js'), define: developmentDefine() })
    },
    announce() {
      developmentRuntime.log('ADMINISTRACIÓN: /admin/reportes (reportes, contenido, cuentas y alertas internas). Avisos sólo en el panel; sin correo, SMS ni publicación ciudadana.')
      developmentRuntime.log('VISOR PREDICTIVO: /admin/predictivo, sólo con sesión de administrador (sin sesión o vencida muestra el ingreso de Administración). /mapa es siempre el mapa público.')
      developmentRuntime.log('Puertos: 5173 frontend · 8767 API administrativa (incluye el visor predictivo, sólo con sesión de administrador). No correr en paralelo con dev:demo.')
      if (service?.adminMissing) developmentRuntime.log(ADMIN_MISSING)
      if (service?.predictiveMissing) developmentRuntime.log(PREDICTIVE_MISSING)
    },
    get service() { return service },
  }
}
