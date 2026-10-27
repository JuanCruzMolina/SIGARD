// Build only generic UI. Private data is injected later by local_query outside frontend.
import { build } from 'vite'
import react from '@vitejs/plugin-react'
import { mkdir, writeFile } from 'node:fs/promises'
import { randomBytes } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const output = resolve(root, '.tmp/predictive-viewer')
const result = await build({
  configFile: false, root, publicDir: false, plugins: [react()],
  define: { 'process.env.NODE_ENV': JSON.stringify('production'), 'import.meta.env.VITE_API_URL': 'undefined' },
  build: { write: false, minify: true, cssCodeSplit: false, sourcemap: false,
    lib: { entry: resolve(root, 'src/predictive-viewer.jsx'), name: 'SigardPrivateViewer', formats: ['iife'] },
    rollupOptions: { output: { inlineDynamicImports: true } } },
})
const files = (Array.isArray(result) ? result : [result]).flatMap(value => value.output)
const scripts = files.filter(file => file.type === 'chunk').map(file => file.code).join('\n')
const styles = files.filter(file => file.type === 'asset' && file.fileName.endsWith('.css')).map(file => String(file.source)).join('\n')
if (!scripts || !styles || /@import|url\(\s*["']?(?:https?:|\/\/)/i.test(styles)) throw new Error('Viewer must be self-contained')
const nonce = randomBytes(18).toString('base64')
const csp = `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'`
const html = `<!doctype html><html lang="es"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${csp}"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SIGARD · Demostración privada</title><style>${styles.replaceAll('</style', '<\\/style')}</style></head><body><div id="root"></div><script id="sigard-private-payload" type="application/json">__SIGARD_PRIVATE_PAYLOAD__</script><script nonce="${nonce}">${scripts.replaceAll('</script', '<\\/script')}</script></body></html>`
await mkdir(output, { recursive: true })
await writeFile(resolve(output, 'viewer.html'), html)
console.log('Generic offline viewer built in frontend/.tmp/predictive-viewer/viewer.html; no private data read.')
