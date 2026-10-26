import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    hmr: {
      protocol: 'ws',
      host: 'localhost',
      port: 5173
    },
    // npm run dev: /api на gateway, браузер остаётся на одном origin (как с nginx).
    // По умолчанию gateway запущен локально без Docker; против compose (gateway наружу не опубликован) —
    // API_PROXY_TARGET=http://localhost:5173
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8000'
    }
  }
})
