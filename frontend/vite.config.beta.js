import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import os from 'node:os'

const __dirname = dirname(fileURLToPath(import.meta.url))

// v2.1.51: version 显式从 start-*.sh 注入, 避免 git describe 分支拓扑 + tag 时间歧义
const VERSION = process.env.VITE_APP_VERSION || 'dev'

// v2.2.2: 自动探测局域网 IP (跨平台, 选第一个非 loopback 私有 IP 172.x/192.x/10.x),
// 让前端 upload chunk 走绝对 URL 直连 uvicorn, 绕过 vite dev proxy 转发
// (bypass Node event loop 串行化, 速度提升 50% + 抖动幅度减 36%, localhost 测 1.5GB/s 稳).
// 可用 VITE_UPLOAD_API 手动指定 (cloudflared 临时域名场景回退到 vite proxy).
//
// v2.2.2-hotfix: 临时禁用 LAN IP 绝对 URL 注入, 强制走 vite proxy 相对路径.
// 原因: user 电脑有 Docker container (172.16.10.x 段) 跟主 wifi (172.16.120.x) 同时在线,
//       detectLanIp 选 172.16.120.82 注入, 但 Docker container 想直连 120.82 跨段路由失败.
//       走 vite proxy (3030) 跨段通过 host gateway 转发, 兼容所有网卡环境.
//       TODO: 修 detectLanIp 跨段路由 + 重新启用绝对 URL 加速.
function detectLanIp() {
  try {
    const ifaces = os.networkInterfaces()
    // 优先 en* (mac/linux ethernet/wifi), 跳过 lo/utun/awdl/llw/br
    const candidates = []
    for (const [name, addrs] of Object.entries(ifaces)) {
      if (/^(lo|utun|awdl|llw|br-|docker|veth|tun|tap|anpi|bridge)/i.test(name)) continue
      for (const a of addrs || []) {
        if (a.family === 'IPv4' && !a.internal) {
          candidates.push({ name, addr: a.address })
        }
      }
    }
    // 优先 172.16-31.x (局域网 B 段), 然后 192.168.x, 然后 10.x
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
// v2.2.2-hotfix2: vite proxy ECONNREFUSED 频繁 (432 次/小时), 走直连 8030 反而稳
// 早 5 个 v2.2.1 init 在 79 段 (同 wifi), 直连 172.16.120.82:8030 OK
// v2.2.2 第一次注入 LAN_IP 失败是 WS path bug, XHR 4 流直连 没问题
const UPLOAD_API = process.env.VITE_UPLOAD_API || (LAN_IP === 'localhost' ? '' : `http://${LAN_IP}:8030`)
// v2.2.2-hotfix: 强制 XHR 路径 (disable WS, 因为 WS 在 OPTIONS preflight 后 PUT 0 个)
const FORCE_XHR = '1'

export default defineConfig({
  plugins: [react()],
  root: __dirname,
  define: {
    __APP_VERSION__: JSON.stringify(VERSION),
    'import.meta.env.VITE_UPLOAD_API': JSON.stringify(UPLOAD_API),
    'import.meta.env.VITE_FORCE_XHR': JSON.stringify(FORCE_XHR),
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
        // v2.2.2: buffer:false 让 vite proxy 不 buffer body, 但 ws 保留默认 true
        // (legacy 浏览器 / cloudflared 走 vite proxy 时, WebSocket upload 端点要升级)
        // VITE_UPLOAD_API 直连 uvicorn 时不走 proxy, 这俩都 work
        buffer: false,
        ws: true,
      },
    },
  },
})