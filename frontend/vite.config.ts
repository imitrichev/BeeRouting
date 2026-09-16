import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // Если 5173 уже занят старым dev-server, Vite не должен незаметно
    // переключаться на другой порт: пользователь должен видеть актуальный UI.
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
