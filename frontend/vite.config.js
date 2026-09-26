import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API is served under /api by FastAPI; the dev server proxies it so the
// session cookie stays same-origin (no CORS, SameSite=Lax works).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_API_TARGET || 'http://localhost:8000', changeOrigin: false } },
  },
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: { three: ['three', '@react-three/fiber'], charts: ['recharts'], vendor: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query', 'framer-motion'] },
      },
    },
  },
})
