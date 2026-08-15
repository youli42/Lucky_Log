import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8666',
      '/ws': { target: 'ws://127.0.0.1:8666', ws: true },
    },
  },
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
  },
})
