import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

// v2.1.51: version 显式从 start-*.sh 注入, 避免 git describe 分支拓扑 + tag 时间歧义
// VITE_APP_VERSION 在 start-beta.sh / start-release.sh 里 export
const VERSION = process.env.VITE_APP_VERSION || 'dev'

export default defineConfig({
  plugins: [react()],
  root: __dirname,
  define: {
    __APP_VERSION__: JSON.stringify(VERSION),
  },
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