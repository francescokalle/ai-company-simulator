import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    target: 'es2020',
    minify: 'esbuild',
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8002',
      '/ws': {
        target: 'ws://localhost:8002',
        ws: true,
      },
    },
  },
})
