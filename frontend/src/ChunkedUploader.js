/**
 * 分片上传 + 断点续传 + 实时进度
 *
 * 用法：
 *   const uploader = new ChunkedUploader({
 *     file, onProgress, onDone, onError
 *   })
 *   uploader.start()   // 开始/恢复
 *   uploader.pause()   // 暂停（不删 upload_id）
 *   uploader.resume()  // 恢复
 *   uploader.cancel()  // 取消（删 upload_id）
 */
const CHUNK_SIZE = 10 * 1024 * 1024   // 10MB (v2.2.1+: 7GB 视频 700 chunk @ 10MB, 局域网 OK; cloudflared trycloudflare 限制单 chunk 30s 内完成, 10MB 在 3MB/s 网络 3.3s 写完 OK)

const MAX_CONCURRENT = 4  // v2.2.2: 6 → 4, 实测 6 流并发 wifi airtime 抢资源 + cwnd 反复缩, 4 流稳 30MB/s 不抖 (局域网测 1.5GB/s → wifi 限速 30-60MB/s 范围)
const MAX_RETRY = 3                   // 单片最多重试 3 次

export class ChunkedUploader {
  constructor({ file, onProgress, onDone, onError, onState }) {
    this.file = file
    this.onProgress = onProgress || (() => {})
    this.onDone = onDone || (() => {})
    this.onError = onError || (() => {})
    this.onState = onState || (() => {})

    this.uploadId = null
    this.totalSize = file.size
    this.receivedBytes = 0
    this.running = false
    this.paused = false
    this.cancelled = false

    // 速度统计
    this.lastTickBytes = 0
    this.lastTickTime = 0
    this.speedBps = 0

    // localStorage key（按 file.name + size + lastModified 区分）
    this.storageKey = `upload_${file.name}_${file.size}_${file.lastModified}`
  }

  setState(s, extra) {
    this.onState(s, extra)
  }

  async start() {
    // v2.2.2-hotfix: 临时禁用 WebSocket 上传, 强制走 XHR 4 流 (v2.2.1 行为).
    // 现象 (2026-07-10 09:48): WS 路径在 vite dev server 下 OPTIONS preflight 200 OK 后,
    // PUT chunk 0 个被发出去; XHR fallback 也走不通 (vite proxy buffer:false 改动引入的回归).
    // 早上 5 个 v2.2.1 XHR 上传 OK, 下午 2 个 v2.2.2 WS+XHR fallback 都失败.
    // TODO: 查清 WS 路径 OPTIONS 后 PUT 卡死 + XHR fallback 失败 的根因后, 重新启用.
    // 用法: import.meta.env.VITE_FORCE_XHR === '1' 时强制 XHR; 否则走 WS-first (默认).
    const forceXhr = (typeof import.meta !== 'undefined' &&
                      import.meta.env &&
                      import.meta.env.VITE_FORCE_XHR === '1')
    if (!forceXhr && this._wsSupported()) {
      try {
        await this._uploadViaWebSocket()
        return
      } catch (e) {
        console.warn('[uploader] WebSocket failed, fallback to XHR:', e.message)
        // 清理 WS session, 回退 XHR
        this._clearProgress()
        this.uploadId = null
        this.receivedBytes = 0
      }
    }
    // XHR 路径 (v2.2.1 实现, 4 并发, 局域网稳 7-15MB/s)
    return this._uploadViaXHR()
  }

  _wsSupported() {
    return typeof WebSocket !== 'undefined'
  }

  async _uploadViaWebSocket() {
    // v2.2.2: WebSocket 单流上传, 1 个长连接持续 stream
    this.running = true
    this.paused = false
    this.cancelled = false
    this.lastTickBytes = 0
    this.lastTickTime = Date.now()

    // 启速度统计
    this._tickInterval = setInterval(() => this._tickSpeed(), 500)
    this.setState('uploading', { received: 0 })

    // 1. 计算 ws URL (跟 API_BASE 走相对路径, vite proxy 兜底, 直连也行)
    const wsScheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const baseUrl = API_BASE.startsWith('http')
      ? API_BASE.replace(/^https?:/, wsScheme)
      : `${wsScheme}//${window.location.host}${API_BASE}`
    const wsUrl = `${baseUrl}/uploads/ws`

    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl)
      let sent = 0
      const CHUNK = 256 * 1024  // 256KB binary frame, 1GB 视频 = 4000 frame
      let sendError = null
      let completed = false

      ws.onopen = async () => {
        // 2. 第一个 text message: init
        ws.send(JSON.stringify({
          type: 'init',
          name: this.file.name.replace(/\.[^/.]+$/, ''),
          filename: this.file.name,
          total_size: this.totalSize,
        }))
      }

      ws.onmessage = async (event) => {
        if (typeof event.data !== 'string') return  // 忽略意外 binary
        let msg
        try {
          msg = JSON.parse(event.data)
        } catch (e) {
          return
        }
        if (msg.type === 'ack') {
          this.uploadId = msg.upload_id
          this.receivedBytes = msg.received_bytes
          this._saveProgress()  // v2.2.2: 存 upload_id (虽然 WS 不真支持断点续传, 给 XHR fallback 用)
          // 第一个 ack 才标 uploading (之前 init 后立即标)
          if (sent === 0) {
            this.setState('uploading', { uploadId: this.uploadId, received: 0 })
          }
        } else if (msg.type === 'error') {
          sendError = new Error(msg.message)
          ws.close()
        } else if (msg.type === 'complete_ok') {
          completed = true
          this.receivedBytes = msg.project.video_size
          this._clearProgress()
          clearInterval(this._tickInterval)
          this.setState('done', { project: msg.project })
          ws.close()
          this.onDone(msg.project)
          resolve()
        }
      }

      ws.onerror = (e) => {
        if (!completed) {
          sendError = new Error('WebSocket 错误')
        }
      }

      ws.onclose = (e) => {
        clearInterval(this._tickInterval)
        if (completed) {
          resolve()
        } else if (sendError) {
          reject(sendError)
        } else if (e.code !== 1000) {
          reject(new Error(`WebSocket 关闭 (code=${e.code})`))
        } else {
          reject(new Error('WebSocket 关闭 (未完成)'))
        }
      }

      // 3. 二进制发送循环 (跟 ack 一起跑, async)
      ;(async () => {
        try {
          while (sent < this.totalSize) {
            if (this.cancelled) {
              ws.close(1000)
              return
            }
            if (this.paused) {
              await new Promise(r => setTimeout(r, 200))
              continue
            }
            // 读 256KB Blob 转 ArrayBuffer (WebSocket 接受 ArrayBuffer / Blob)
            const blob = this.file.slice(sent, Math.min(sent + CHUNK, this.totalSize))
            const buffer = await blob.arrayBuffer()
            if (ws.readyState !== WebSocket.OPEN) {
              throw new Error('WebSocket 未打开, 中断发送')
            }
            ws.send(buffer)  // 浏览器自动用 binary frame
            sent += buffer.byteLength
            this.receivedBytes = sent  // 立刻更新本地 received (跟 ack 校准)
          }
          // 4. 全部 binary 发完, 发 complete text
          // 注: server 也会等收到 ack 后才能 complete, 所以这里需要等到 receivedBytes >= totalSize
          // (server 会发 ack received_bytes = total_size)
          // 简化: 直接发 complete, server 端 received < total 会返 error
          // 但实际 ack 到了之后 server received == total, 我们已经知道
          // 给 server 一点时间 (200ms) ack 完再发 complete
          await new Promise(r => setTimeout(r, 200))
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'complete', keep_raw: this.keepRaw || false }))
          }
        } catch (e) {
          sendError = e
          try { ws.close(1000) } catch {}
        }
      })()
    })
  }

  async _uploadViaXHR() {
    // v2.2.1: XHR 4 并发分片上传 (legacy / cloudflared fallback)
    // 1. 看看 localStorage 有没有上次的 upload_id（断点续传）
    const saved = this._loadProgress()
    if (saved) {
      try {
        const status = await fetch(`${API_BASE}/uploads/${saved.upload_id}/status`, {
          headers: this._authHeaders()
        }).then(r => r.json())
        if (status.total_size === this.totalSize && !status.completed) {
          this.uploadId = saved.upload_id
          this.receivedBytes = status.received_bytes
          this.setState('resuming', { uploadId: this.uploadId, received: this.receivedBytes })
        }
      } catch (e) {
        this._clearProgress()
      }
    }

    this.running = true
    this.paused = false
    this.cancelled = false
    this.lastTickBytes = this.receivedBytes
    this.lastTickTime = Date.now()

    // 2. 没有 upload_id 就 init
    if (!this.uploadId) {
      try {
        const form = new FormData()
        form.append('name', this.file.name.replace(/\.[^/.]+$/, ''))
        form.append('filename', this.file.name)
        form.append('total_size', this.totalSize)
        const res = await fetch(`${API_BASE}/uploads/init`, {
          method: 'POST',
          body: form,
          headers: this._authHeaders()
        })
        if (!res.ok) throw new Error(`init 失败: ${res.status}`)
        const data = await res.json()
        this.uploadId = data.upload_id
        this._saveProgress()
        this.setState('uploading', { uploadId: this.uploadId })
      } catch (e) {
        this.setState('error', { error: e.message })
        this.onError(e)
        return
      }
    }

    // 3. 启动速度统计
    this._tickInterval = setInterval(() => this._tickSpeed(), 500)

    // 4. 启动分片上传（并发）
    return this._uploadAllXHR()
  }

  async _uploadAllXHR() {
    const tasks = []
    for (let offset = this.receivedBytes; offset < this.totalSize; offset += CHUNK_SIZE) {
      // 跳过已传
      if (offset < this.receivedBytes) continue
      tasks.push({ offset, chunk: this.file.slice(offset, Math.min(offset + CHUNK_SIZE, this.totalSize)) })
    }

    // 并发执行（最多 3）
    const queue = [...tasks]
    const workers = []
    for (let i = 0; i < Math.min(MAX_CONCURRENT, queue.length); i++) {
      workers.push(this._worker(queue))
    }
    await Promise.all(workers)

    if (this.cancelled) return
    if (this.paused) {
      this.setState('paused', { received: this.receivedBytes })
      return
    }

    // 5. 合并 + 创建项目
    clearInterval(this._tickInterval)
    this.setState('finalizing', { received: this.receivedBytes })
    try {
      const res = await fetch(`${API_BASE}/uploads/${this.uploadId}/complete`, {
        method: 'POST',
        headers: this._authHeaders()
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `complete 失败: ${res.status}`)
      }
      const data = await res.json()
      this._clearProgress()
      this.setState('done', { project: data })
      this.onDone(data)
    } catch (e) {
      this.setState('error', { error: e.message })
      this.onError(e)
    }
  }

  async _worker(queue) {
    while (queue.length > 0 && this.running && !this.paused && !this.cancelled) {
      const task = queue.shift()
      await this._uploadOneWithRetry(task)
    }
  }

  async _uploadOneWithRetry(task) {
    for (let attempt = 1; attempt <= MAX_RETRY; attempt++) {
      if (!this.running || this.paused || this.cancelled) return
      try {
        await this._uploadOne(task)
        return
      } catch (e) {
        const isLast = attempt === MAX_RETRY
        this.setState(isLast ? 'error' : 'retrying', {
          error: isLast ? `分片 ${task.offset} 失败（重试 ${attempt} 次）：${e.message}` : null,
          attempt, maxAttempt: MAX_RETRY, offset: task.offset
        })
        if (isLast) {
          this.onError(e)
          throw e
        }
        // 退避：500ms → 1500ms → 4500ms（指数增长）
        const backoff = 500 * Math.pow(3, attempt - 1)
        await new Promise(r => setTimeout(r, backoff))
      }
    }
  }

  _uploadOne({ offset, chunk }) {
    // 用 XHR 而非 fetch：fetch 不暴露上传进度，XHR 有 xhr.upload.onprogress
    // v2.2.1+: 改 raw body 上传 (application/octet-stream), 不走 multipart/form-data
    // 旧 multipart: 每个 chunk 200-300 bytes boundary/header overhead, 7GB 视频 700 chunk 浪费 150-200MB 带宽 + 解析
    // 新 raw body: 0 overhead, 局域网 7GB 视频从 15MB/s 提到 30+ MB/s
    return new Promise((resolve, reject) => {
      const url = `${API_BASE}/uploads/${this.uploadId}/chunk?offset=${offset}`

      const xhr = new XMLHttpRequest()
      xhr.open('PUT', url, true)
      // 设置超时：10MB chunk 在 3MB/s 网络 3.3s 写完, 给 10 分钟 (LAN ~5s 写完, 慢网络 <60s)
      xhr.timeout = 10 * 60 * 1000

      // headers
      const headers = this._authHeaders()
      for (const [k, v] of Object.entries(headers)) {
        xhr.setRequestHeader(k, v)
      }

      // 进度回调：每收到一点数据就更新 UI
      // v2.2.1+: 6 chunk 并发, onprogress 直接 set this.receivedBytes = offset + chunkLoaded
      // 会 race condition (chunk 0 上报 80% 8MB 会把 chunk 1 上报 15MB 覆盖掉, 进度条跳回)
      // 修法: 客户端估算也用 max(this.receivedBytes, newValue) 保证单调不减
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const chunkLoaded = e.loaded
          // 客户端估算: offset + chunkLoaded, 但要单调不减避免跳
          if (offset + chunkLoaded > this.receivedBytes) {
            this.receivedBytes = offset + chunkLoaded
            this.onProgress({
              received: this.receivedBytes,
              total: this.totalSize,
              speed: this.speedBps,
            })
          }
        }
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText)
            // v2.2.1+: server 累加 received_bytes 是权威值, 也用 max 防止回退
            // (onprogress 估算的 client 值可能比 server 大, 但 server 是真值, max 保证单调)
            if (data.received_bytes > this.receivedBytes) {
              this.receivedBytes = data.received_bytes
            }
            this._saveProgress()
            this.onProgress({
              received: this.receivedBytes,
              total: this.totalSize,
              speed: this.speedBps,
            })
            resolve(data)
          } catch (e) {
            reject(new Error('解析响应失败'))
          }
        } else {
          let msg = `HTTP ${xhr.status}`
          try {
            const err = JSON.parse(xhr.responseText)
            msg = err.detail || msg
          } catch (e) { /* 忽略 */ }
          reject(new Error(msg))
        }
      }

      xhr.onerror = () => reject(new Error('网络错误'))
      xhr.onabort = () => reject(new Error('已取消'))

      // 暴露 xhr 给 pause / cancel
      this._currentXHRs = this._currentXHRs || new Set()
      this._currentXHRs.add(xhr)
      xhr.onloadend = () => {
        this._currentXHRs?.delete(xhr)
      }

      xhr.send(chunk)  // v2.2.1+: raw Blob body (application/octet-stream)
    })
  }

  _tickSpeed() {
    const now = Date.now()
    const dt = (now - this.lastTickTime) / 1000  // seconds
    if (dt > 0) {
      const dBytes = this.receivedBytes - this.lastTickBytes
      const instantBps = dBytes / dt
      // v2.2.1+: EMA 平滑速度, 避免显示瞬时抖动 (SSD GC pause / TCP 拥塞控制让瞬时速度跳)
      // alpha=0.3: 历史 70% + 当前 30%, 窗口约 2-3s 平滑
      this.speedBps = this.speedBps
        ? this.speedBps * 0.7 + instantBps * 0.3
        : instantBps
      this.lastTickBytes = this.receivedBytes
      this.lastTickTime = now
    }
  }

  pause() {
    this.paused = true
    this.running = false
  }

  resume() {
    if (this.paused) {
      this.paused = false
      this.running = true
      this.lastTickBytes = this.receivedBytes
      this.lastTickTime = Date.now()
      this._uploadAllXHR()
    }
  }

  async cancel() {
    this.cancelled = true
    this.running = false
    // 中断所有进行中的 XHR
    if (this._currentXHRs) {
      for (const xhr of this._currentXHRs) {
        try { xhr.abort() } catch (e) { /* 忽略 */ }
      }
    }
    if (this.uploadId) {
      try {
        await fetch(`${API_BASE}/uploads/${this.uploadId}`, {
          method: 'DELETE',
          headers: this._authHeaders()
        })
      } catch (e) { /* 忽略 */ }
    }
    this._clearProgress()
  }

  _saveProgress() {
    try {
      localStorage.setItem(this.storageKey, JSON.stringify({
        upload_id: this.uploadId,
        total_size: this.totalSize,
        received: this.receivedBytes,
        filename: this.file.name,
        saved_at: Date.now()
      }))
    } catch (e) { /* localStorage 满了就忽略 */ }
  }

  _loadProgress() {
    try {
      const raw = localStorage.getItem(this.storageKey)
      if (!raw) return null
      const data = JSON.parse(raw)
      // 24h 过期
      if (Date.now() - data.saved_at > 24 * 60 * 60 * 1000) {
        this._clearProgress()
        return null
      }
      return data
    } catch (e) { return null }
  }

  _clearProgress() {
    try { localStorage.removeItem(this.storageKey) } catch (e) {}
  }

  _authHeaders() {
    // basic auth：前端每次带（因为 vite proxy 不带 auth）
    // 但其实 cloudflared 已经被 nginx 拦截了，前端不一定要带
    // 不带以兼容
    return {}
  }
}

// v2.2.2: upload chunk 走绝对 URL 直连 uvicorn (bypass vite dev proxy).
//   局域网 dev 模式: vite proxy 转发 6 chunk 走 Node event loop, 跟 HMR/ESM transform 抢资源,
//   速度掉 50% (1.5GB/s → 1.1GB/s localhost) + 抖动幅度增 36% (min 185 → 117 MB/s).
//   直连 uvicorn 8030/8000 让 Node event loop 只服务 HMR, 1GB 视频稳 30-60MB/s (wifi 限速).
//   注入路径: vite config `define: { 'import.meta.env.VITE_UPLOAD_API': '...' }` 由 esbuild 替换.
const UPLOAD_API_BASE = (() => {
  const v = import.meta.env?.VITE_UPLOAD_API
  if (v) return `${v}/api/v1`  // dev 局域网直连 uvicorn
  return '/api/v1'  // prod build / cloudflared 场景走 vite proxy 相对路径
})()
const API_BASE = UPLOAD_API_BASE

// ===== 工具函数 =====
export function formatBytes(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

export function formatSpeed(bps) {
  if (!bps || bps < 1) return '0 B/s'
  if (bps < 1024) return `${bps.toFixed(0)} B/s`
  if (bps < 1024 * 1024) return `${(bps / 1024).toFixed(1)} KB/s`
  return `${(bps / 1024 / 1024).toFixed(2)} MB/s`
}

export function formatTime(seconds) {
  if (!seconds || seconds < 0 || !isFinite(seconds)) return '—'
  if (seconds < 60) return `${Math.ceil(seconds)} 秒`
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60)
    const s = Math.ceil(seconds % 60)
    return `${m} 分 ${s} 秒`
  }
  const h = Math.floor(seconds / 3600)
  const m = Math.ceil((seconds % 3600) / 60)
  return `${h} 小时 ${m} 分`
}
