import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { publicAssetSafety } from './security/public-assets.mjs'

// https://vite.dev/config/
export default defineConfig({
  plugins: [publicAssetSafety(), react()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
})
