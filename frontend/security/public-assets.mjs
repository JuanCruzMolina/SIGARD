// Security boundary for existing static MVP resources; no epidemiological inference.
import { createHash } from 'node:crypto'
import { lstatSync, readFileSync, readdirSync } from 'node:fs'
import { extname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const approvedPublicAssets = JSON.parse(readFileSync(new URL('./public-assets.json', import.meta.url), 'utf8')).assets
const frontendRoot = fileURLToPath(new URL('../', import.meta.url))
const message = 'Static resource security check failed; review locally before serving or building.'

function deny() { throw new Error(message) }

function filesIn(directory, prefix = '') {
  if (!lstatSync(directory).isDirectory() || lstatSync(directory).isSymbolicLink()) deny()
  const files = []
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name)
    const relative = prefix + entry.name
    if (entry.isSymbolicLink() || lstatSync(path).isSymbolicLink()) deny()
    if (entry.isDirectory()) files.push(...filesIn(path, relative + '/'))
    else if (entry.isFile()) files.push(relative)
    else deny()
  }
  return files.sort()
}

export function normalizedHash(path) {
  const info = lstatSync(path)
  if (!info.isFile() || info.isSymbolicLink() || info.size > 8 * 1024 * 1024) deny()
  const text = new TextDecoder('utf-8', { fatal: true }).decode(readFileSync(path))
  return createHash('sha256').update(text.replace(/\r\n/g, '\n')).digest('hex')
}

export function assertApprovedPublic(directory, approved = approvedPublicAssets) {
  const expected = Object.keys(approved).sort()
  const actual = filesIn(directory)
  if (JSON.stringify(actual) !== JSON.stringify(expected)) deny()
  for (const name of actual) {
    if (normalizedHash(resolve(directory, name)) !== approved[name]) deny()
  }
  return { approvedFiles: actual.length }
}

export function assertApprovedDistribution(directory, approved = approvedPublicAssets) {
  const files = filesIn(directory)
  for (const name of files) {
    if (Object.hasOwn(approved, name)) {
      if (normalizedHash(resolve(directory, name)) !== approved[name]) deny()
    } else if (name !== 'index.html' && !(name.startsWith('assets/') &&
      ['.js', '.css', '.png', '.svg', '.woff', '.woff2'].includes(extname(name)) &&
      !/(?:private|confidential|patient|paciente|\.env)/i.test(name))) deny()
  }
  if (!files.includes('index.html') || Object.keys(approved).some((name) => !files.includes(name))) deny()
  return { approvedFiles: Object.keys(approved).length }
}

export function safetyMiddleware(check) {
  return (_request, response, next) => {
    try { check(); next() } catch {
      response.statusCode = 503
      response.setHeader('Content-Type', 'text/plain; charset=utf-8')
      response.setHeader('Cache-Control', 'no-store')
      response.end(message)
    }
  }
}

export function publicAssetSafety() {
  let config
  const protectedPatterns = [
    '**/.git/**', '**/.env', '**/.env.*', '**/*.env', '**/*.env.*',
    '**/*.private', '**/*.private.*', '**/*.private-*', '**/*_private*',
    '**/private/**', '**/confidential/**', '**/secrets/**', '**/.agents/**',
    '**/.npmrc', '**/.yarnrc.yml', '**/.netrc', '**/.pypirc', '**/.git-credentials',
    '**/.aws/**', '**/.ssh/**', '**/.azure/**', '**/.kube/**', '**/.docker/**',
    '**/*.xls*', '**/*.{parquet,feather,arrow,csv,tsv,joblib,pkl,pickle,h5,hdf5,onnx,pt,pth}',
    '**/*.{geojson,gpkg,shp,shx,dbf,prj,kml,kmz,gpx}',
    '**/*.{crt,pem,key,p12,pfx,cer,der,keystore}', '**/credentials.{json,yaml,yml,toml,ini}', '**/secrets.{json,yaml,yml}',
  ]
  const denyPatterns = protectedPatterns.flatMap((pattern) => [pattern, pattern.replace(/[a-z]/g, (letter) => `[${letter}${letter.toUpperCase()}]`)])
  const checkPublic = () => assertApprovedPublic(resolve(config.root, 'public'))
  const checkDistribution = () => assertApprovedDistribution(resolve(config.root, config.build.outDir))
  return {
    name: 'sigard-public-asset-safety',
    enforce: 'pre',
    config(rawConfig) {
      return { server: { fs: { strict: true, allow: [resolve(rawConfig.root || frontendRoot)], deny: denyPatterns } } }
    },
    configResolved(resolved) {
      config = resolved
      if (resolve(config.publicDir) !== resolve(config.root, 'public')) deny()
      checkPublic()
    },
    buildStart() { checkPublic() },
    configureServer(server) {
      // Runs before Vite's public middleware, including files added after startup.
      server.middlewares.use(safetyMiddleware(checkPublic))
    },
    configurePreviewServer(server) {
      checkDistribution()
      server.middlewares.use(safetyMiddleware(() => { checkPublic(); checkDistribution() }))
    },
    closeBundle() {
      if (config?.command === 'build') { checkPublic(); checkDistribution() }
    },
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  assertApprovedPublic(resolve(frontendRoot, 'public'))
  console.log('Approved public assets verified; no files modified.')
}
