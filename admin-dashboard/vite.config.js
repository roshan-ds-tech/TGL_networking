import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Built straight into the backend so FastAPI serves the dashboard same-origin.
// That is what lets the session cookie stay HttpOnly + SameSite=Strict.
export default defineConfig({
  plugins: [react()],
  base: '/admin/',
  build: {
    outDir: '../backend/static/admin',
    emptyOutDir: true,
  },
  server: {
    port: 5174,
    // In dev the API is proxied so the browser still sees a single origin.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
});
