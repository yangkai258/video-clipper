import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  root: __dirname,
  server: {
    host: '0.0.0.0',
    port: 3030,
    // 允许 cloudflared 临时域名（每次启动会变）
    allowedHosts: true,  // 接受所有 Host 头（开发用）
    proxy: {
      '/api': {
        target: 'http://localhost:8030',
        changeOrigin: true,
      },
    },
  },
})
