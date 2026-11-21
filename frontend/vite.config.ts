import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // KRONOS backend (FastAPI) — run: python -m uvicorn kronos.api.main:app --port 8000
    proxy: {
      '/api': { target: process.env.KRONOS_API_URL || 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});
