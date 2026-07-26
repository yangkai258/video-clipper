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
const CHUNK_SIZE = 1 * 1024 * 1024   // 1MB（cloudflared trycloudflare 限制：单 chunk 30s 内必须完成）
const MAX_CONCURRENT = 1              // 单并发：避免抢带宽
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
        // status 查询失败——重新上传
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
    this._uploadAll()
  }

  async _uploadAll() {
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
    return new Promise((resolve, reject) => {
      const form = new FormData()
      form.append('chunk', chunk, 'chunk')
      const url = `${API_BASE}/uploads/${this.uploadId}/chunk?offset=${offset}`

      const xhr = new XMLHttpRequest()
      xhr.open('PUT', url, true)
      // 设置超时：50MB chunk 给 10 分钟（5MB/s 已经够宽裕）
      xhr.timeout = 10 * 60 * 1000

      // headers（不带 Content-Type，让浏览器自动加 multipart 边界）
      const headers = this._authHeaders()
      for (const [k, v] of Object.entries(headers)) {
        xhr.setRequestHeader(k, v)
      }

      // 进度回调：每收到一点数据就更新 UI
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          // 本片已上传 + 之前所有完整片的累计
          const chunkLoaded = e.loaded
          this.receivedBytes = offset + chunkLoaded
          this.onProgress({
            received: this.receivedBytes,
            total: this.totalSize,
            speed: this.speedBps,
          })
        }
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText)
            this.receivedBytes = data.received_bytes
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

      xhr.send(form)
    })
  }

  _tickSpeed() {
    const now = Date.now()
    const dt = (now - this.lastTickTime) / 1000  // seconds
    if (dt > 0) {
      const dBytes = this.receivedBytes - this.lastTickBytes
      this.speedBps = dBytes / dt
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
      this._uploadAll()
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
    try { localStorage.removeItem(this.storageKey) } catch (_e) { void _e }
  }

  _authHeaders() {
    // basic auth：前端每次带（因为 vite proxy 不带 auth）
    // 但其实 cloudflared 已经被 nginx 拦截了，前端不一定要带
    // 不带以兼容
    return {}
  }
}

const API_BASE = '/api/v1'

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
