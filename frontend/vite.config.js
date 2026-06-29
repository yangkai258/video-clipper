import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// v2.1.51: version 显式从 start-*.sh 注入
const VERSION = process.env.VITE_APP_VERSION || 'dev'

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(VERSION),
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})