import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import os from 'node:os'

// v2.1.51: version 显式从 start-*.sh 注入
const VERSION = process.env.VITE_APP_VERSION || 'dev'

// v2.2.2: 自动探测局域网 IP (跨平台, 选第一个非 loopback 私有 IP)
function detectLanIp() {
  try {
    const ifaces = os.networkInterfaces()
    const candidates = []
    for (const [name, addrs] of Object.entries(ifaces)) {
      if (/^(lo|utun|awdl|llw|br-|docker|veth|tun|tap|anpi|bridge)/i.test(name)) continue
      for (const a of addrs || []) {
        if (a.family === 'IPv4' && !a.internal) {
          candidates.push({ name, addr: a.address })
        }
      }
    }
    const privateNet = candidates.find(c => /^172\.(1[6-9]|2[0-9]|3[01])\./.test(c.addr))
                || candidates.find(c => /^192\.168\./.test(c.addr))
                || candidates.find(c => /^10\./.test(c.addr))
                || candidates[0]
    return privateNet?.addr || 'localhost'
  } catch {
    return 'localhost'
  }
}
const LAN_IP = process.env.LAN_IP || detectLanIp()
// v2.2.2-hotfix2: vite proxy ECONNREFUSED 频繁, 走直连 8000 反而稳
const UPLOAD_API = process.env.VITE_UPLOAD_API || (LAN_IP === 'localhost' ? '' : `http://${LAN_IP}:8000`)
// v2.2.2-hotfix: 强制 XHR 路径 (disable WS, 因为 WS 在 OPTIONS preflight 后 PUT 0 个)
const FORCE_XHR = '1'

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(VERSION),
    'import.meta.env.VITE_UPLOAD_API': JSON.stringify(UPLOAD_API),
    'import.meta.env.VITE_FORCE_XHR': JSON.stringify(FORCE_XHR),
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // v2.2.2: buffer:false 不 buffer body, ws 保留默认 true (legacy fallback 需要)
        buffer: false,
        ws: true,
      },
    },
  },
})