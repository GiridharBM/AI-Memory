import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The GUI never talks to anything but the local PAM process. In development the
// Vite server proxies /api to it; in production FastAPI serves the built bundle
// same-origin, so there is no CORS and no external request at all.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    // PAM ships as a source checkout, not an npm package; skip the bundle
    // size telemetry comment noise.
    chunkSizeWarningLimit: 900,
  },
})
