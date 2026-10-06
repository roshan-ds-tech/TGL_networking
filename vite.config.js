import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Member photos are served by the API at same-origin paths (/api/v1/...).
    // In production the host proxies them; in dev this does the same, so an
    // <img src="/api/..."> reaches the backend instead of Vite's own 404.
    proxy: {
      '/api': { target: process.env.VITE_API_URL || 'http://localhost:8000', changeOrigin: false },
    },
  },
})
