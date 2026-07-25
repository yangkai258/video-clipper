import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// v2.2.15: vitest 配置 (前端测试)
// jsdom 模拟浏览器环境, @testing-library/react 渲染 React 组件测
// CSS / 静态资源 mock 避免 vitest 找不到 import
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
    // 6 个核心组件 test, 跑 < 10s
    include: ['src/**/*.test.{js,jsx}'],
  },
})
