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
    // npm run dev без Docker: /api на gateway, браузер остаётся на одном origin (как с nginx)
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
