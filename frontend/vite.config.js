import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 从环境变量读取配置，支持正式版/测试版并行运行
const PORT = parseInt(process.env.VITE_PORT || '3030', 10)
const API_PORT = parseInt(process.env.VITE_API_PORT || '8030', 10)

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: PORT,
    proxy: {
      '/api': {
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
      },
    },
  },
})
