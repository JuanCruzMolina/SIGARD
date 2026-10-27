import { mkdir, mkdtemp, rm, access } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { developmentRuntime, portAvailable, spawnOwned, startDevelopment } from './dev.mjs'

const frontend = dirname(dirname(fileURLToPath(import.meta.url)))
const repository = dirname(frontend)
const backend = join(repository, 'backend')
const python = join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const api = 'http://127.0.0.1:8766'

export function demoOfflineStyles() {
  return {
    name: 'sigard-demo-offline-fonts', enforce: 'pre',
    transform(code, id) {
      if (id.split('?')[0].replaceAll('\\', '/') !== join(frontend, 'src/index.css').replaceAll('\\', '/')) return
      return code.replace(/^@import url\('https:\/\/fonts\.googleapis\.com\/[^']+'\);\r?\n/m, '')
    },
  }
}

export function demoEnvironment(source = process.env) {
  const env = { ...source, PYTHONIOENCODING: 'utf-8' }
  for (const key of Object.keys(env)) {
    if (/^(PG|SIGARD_POSTGIS|PYTHONPATH|PYTHONSTARTUP)/i.test(key)
      || /^(DATABASE_URL|SIGARD_TEST_POSTGRES_URL|SECRET_KEY|ADMIN_BOOTSTRAP_EMAIL|ADMIN_BOOTSTRAP_PASSWORD)$/i.test(key)) delete env[key]
  }
  return env
}

export function createDemoService() {
  let child, directory, credentials, stopping, finishExit, childExited = false
  const exited = new Promise(resolve => { finishExit = resolve })
  const prepared = (async () => {
    await mkdir(join(backend, '.tmp'), { recursive: true })
    directory = await mkdtemp(join(backend, '.tmp', 'sigard-demo-'))
    child = spawnOwned(python, ['-I', '-B', join(backend, 'app/demo_local.py'), '--directory', directory], {
      cwd: directory, env: demoEnvironment(), input: true, silent: true,
    })
    child.exited.then(result => { childExited = true; finishExit(result) })
    // Neither logs nor credentials from this private pipe are persisted.
    child.stderr.resume()
    child.stdin.on('error', () => {}) // Child may exit before a shutdown write.
    return child
  })()
  const ready = (async () => {
    try {
      await prepared
      const session = await Promise.race([
        new Promise((resolve, reject) => {
          let buffer = ''
          child.stdout.on('data', data => {
            buffer += data.toString()
            if (buffer.length > 4096) return reject(new Error('Respuesta demo inválida.'))
            if (buffer.includes('\n')) {
              try { resolve(JSON.parse(buffer.split('\n')[0])) } catch { reject(new Error('Respuesta demo inválida.')) }
            }
          })
        }),
        exited.then(() => { throw new Error('La API demo terminó antes de estar lista. Revisá las dependencias backend y el puerto 8766.') }),
        delay(15000, null, { ref: false }).then(() => { throw new Error('La API demo no inició en 15 segundos.') }),
      ])
      if (!/^demo-[a-f0-9]+@example\.test$/.test(session.email) || typeof session.password !== 'string'
        || session.password.length < 24 || typeof session.session !== 'string') throw new Error('Sesión demo inválida.')
      const deadline = Date.now() + 15000
      while (true) {
        if (childExited) throw new Error('La API demo terminó durante la inicialización.')
        try {
          const response = await fetch(`${api}/health/demo`, { redirect: 'error', signal: AbortSignal.timeout(1000) })
          const health = await response.json()
          if (response.ok && health.demo === true && health.storage === 'disposable-sqlite' && health.session === session.session) break
        } catch { /* Await only the child identified by its random session nonce. */ }
        if (Date.now() >= deadline) throw new Error('La API demo no estuvo lista; puerto 8766 o inicialización inválida.')
        await delay(100)
      }
      const response = await fetch(`${api}/health/ready`, { redirect: 'error', signal: AbortSignal.timeout(2000) })
      if (!response.ok) throw new Error('El esquema SQLite demo no está disponible.')
      credentials = { email: session.email, password: session.password }
    } catch (error) {
      finishExit({ error: true })
      throw error
    }
  })()
  return {
    ready, exited,
    get directory() { return directory },
    get credentials() { return credentials },
    stop() {
      stopping ??= (async () => {
        await prepared.catch(() => {})
        if (child) {
          child.stdin.end('stop\n')
          const graceful = await Promise.race([child.exited.then(() => true), delay(5000, false, { ref: false })])
          if (!graceful) await child.stop()
          await child.exited
        }
        credentials = undefined
        // This exact path was created by mkdtemp above, never read from settings.
        if (directory) await rm(directory, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 })
      })()
      return stopping
    },
  }
}

export function demoRuntime() {
  let service
  return {
    ...developmentRuntime,
    research: false,
    async checkRequirements() {
      if (!await portAvailable(8766)) throw new Error('El puerto 127.0.0.1:8766 está ocupado. La demo no reutiliza ni detiene ese servicio.')
      await developmentRuntime.ensurePython()
      // Check imports without dotenv, app.main or database connections.
      const check = spawnOwned(python, ['-I', '-B', '-c', 'import fastapi, uvicorn, sqlalchemy, geoalchemy2, pydantic_settings, jose, passlib, httpx, pyarrow'], {
        cwd: backend, env: demoEnvironment(), silent: true,
      })
      check.stdout.resume(); check.stderr.resume()
      const result = await Promise.race([check.exited, delay(15000, null, { ref: false })])
      if (!result || result.code !== 0) {
        await check.stop()
        throw new Error('Faltan requisitos de backend/requirements.research.txt o no se pudieron comprobar.')
      }
      await access(join(frontend, 'node_modules/vite/package.json'))
    },
    startCompanion() { service = createDemoService(); return service },
    async createVite() {
      const { createServer } = await import('vite')
      return createServer({
        root: frontend, configFile: join(frontend, 'vite.config.js'),
        plugins: [demoOfflineStyles()],
        define: { 'import.meta.env.SIGARD_DEMO': 'true', 'import.meta.env.VITE_API_URL': JSON.stringify(api) },
      })
    },
    announce() {
      developmentRuntime.log('DEMO FICTICIA Y TEMPORAL: prevención/seguimiento en /prevencion · análisis, ingestión y alertas en /admin/reportes.')
      developmentRuntime.log('SQLite se elimina al salir; usá sólo contenido inventado y ubicación manual. Las cuentas no corresponden a personas reales.')
      // Display once, only in the local terminal. Never put these in a file/URL.
      developmentRuntime.log(`Cuenta de esta sesión: ${service.credentials.email}\nContraseña temporal: ${service.credentials.password}`)
    },
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv.length > 2) throw new Error('Ejecutá npm run dev:demo sin argumentos; hosts y puertos son fijos.')
    const session = await startDevelopment(demoRuntime())
    process.exitCode = await session.closed
  } catch (error) {
    console.error(`[SIGARD] ${error.message}`)
    process.exitCode = 1
  }
}
