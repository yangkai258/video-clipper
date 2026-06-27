import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import axios from 'axios'
import { ChunkedUploader, formatBytes, formatSpeed, formatTime } from './ChunkedUploader'
import './index.css'

function App() {
  const [projects, setProjects] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState({ received: 0, total: 0, speed: 0 })
  const [uploadState, setUploadState] = useState('idle')  // idle | uploading | pausing | paused | resuming | finalizing | done | error
  const [uploadError, setUploadError] = useState('')
  const uploaderRef = useRef(null)
  const [showStrategyModal, setShowStrategyModal] = useState(false)
  const [pendingProject, setPendingProject] = useState(null)
  const [presets, setPresets] = useState([])
  const [customStyles, setCustomStyles] = useState([])
  const [withSubtitle, setWithSubtitle] = useState(true)
  const [activeTab, setActiveTab] = useState('all')
  const [search, setSearch] = useState('')
  const navigate = useNavigate()
  const location = useLocation()

  const API_BASE = '/api/v1'

  const loadProjects = async () => {
    try {
      const res = await axios.get(`${API_BASE}/projects/`)
      setProjects(res.data.projects)
    } catch (e) {
      console.error('加载项目失败:', e)
    }
  }

  const loadStrategies = async () => {
    try {
      const [p, s] = await Promise.all([
        axios.get(`${API_BASE}/strategies/presets`),
        axios.get(`${API_BASE}/styles`)
      ])
      setPresets(p.data.strategies)
      setCustomStyles(s.data)
    } catch (e) { console.error(e) }
  }

  useEffect(() => {
    loadProjects()
    loadStrategies()
    const id = setInterval(loadProjects, 5000)
    return () => clearInterval(id)
  }, [])

  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    // 重置 input，下次选同一个文件能触发 change
    e.target.value = ''

    const name = prompt('项目名称：', file.name.replace(/\.[^/.]+$/, ''))
    if (!name) return
    setUploading(true)
    setUploadError('')
    setUploadProgress({ received: 0, total: file.size, speed: 0 })
    setUploadState('uploading')

    const uploader = new ChunkedUploader({
      file: new File([file], filename_safe(name) + ext_of(file.name), { type: file.type }),
      onProgress: (p) => setUploadProgress(p),
      onState: (s, extra) => {
        setUploadState(s)
        if (s === 'error') setUploadError(extra?.error || '未知错误')
      },
      onDone: (data) => {
        setUploading(false)
        setUploadState('done')
        setPendingProject({ id: data.project_id, name })
        setShowStrategyModal(true)
        loadProjects()
      },
      onError: (err) => {
        // 错误时不要隐藏进度条——让用户看到错误信息
        setUploadState('error')
        setUploadError(err.message)
      },
    })
    uploaderRef.current = uploader
    uploader.start()
  }

  const handlePause = () => {
    if (uploaderRef.current && uploadState === 'uploading') {
      uploaderRef.current.pause()
      setUploadState('paused')
    }
  }

  const handleResume = () => {
    if (uploaderRef.current && uploadState === 'paused') {
      setUploadState('resuming')
      uploaderRef.current.resume()
    }
  }

  const handleCancel = async () => {
    if (!uploaderRef.current) return
    if (!confirm('确定取消上传吗？已传的分片会丢失。')) return
    await uploaderRef.current.cancel()
    setUploading(false)
    setUploadState('idle')
    setUploadProgress({ received: 0, total: 0, speed: 0 })
  }

  function filename_safe(s) {
    return s.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80) || 'untitled'
  }
  function ext_of(name) {
    const i = name.lastIndexOf('.')
    return i > 0 ? name.slice(i) : ''
  }

  const selectStrategy = async (strategy) => {
    if (!pendingProject) return
    setShowStrategyModal(false)
    try {
      const isCustom = strategy.id.startsWith('style_')
      await axios.put(`${API_BASE}/projects/${pendingProject.id}/config`, {
        with_subtitle: withSubtitle,
        ...(isCustom && {
          style_id: strategy.id,
          strategy_name: strategy.name,
          target_duration: strategy.target_duration,
          max_clips: strategy.max_clips,
          content_types: strategy.content_types,
          rules: strategy.rules,
          content_guidelines: strategy.content_guidelines,
          keep_rules: strategy.keep_rules,
          remove_rules: strategy.remove_rules,
          style_positioning: strategy.style_positioning,
          subtitle_style: strategy.subtitle_config || null,
        })
      })
    } catch (e) { console.error('配置失败：', e) }

    try {
      await axios.post(`${API_BASE}/projects/${pendingProject.id}/process`)
      loadProjects()
    } catch (e) {
      alert(`处理失败：${e.response?.data?.detail || e.message}`)
    }
    setPendingProject(null)
  }

  const startProcessing = async (id) => {
    try {
      await axios.post(`${API_BASE}/projects/${id}/process`)
      loadProjects()
    } catch (e) {
      alert(`启动失败：${e.response?.data?.detail || e.message}`)
    }
  }

  const deleteProject = async (id, name) => {
    if (!confirm(`确定删除「${name}」？此操作不可恢复。`)) return
    try {
      await axios.delete(`${API_BASE}/projects/${id}`)
      loadProjects()
    } catch (e) { alert(`删除失败：${e.message}`) }
  }

  const formatTC = (s) => {
    if (!s) return '00:00'
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  }

  const formatDate = (iso) => {
    if (!iso) return '—'
    return new Date(iso + 'Z').toLocaleString('zh-CN', {
      timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
    })
  }

  const statusLabel = {
    pending: '待处理',
    processing: '处理中',
    completed: '已完成',
    failed: '失败'
  }

  const filteredProjects = projects.filter(p => {
    if (activeTab === 'all') return true
    if (activeTab === 'processing') return p.status === 'processing'
    if (activeTab === 'completed') return p.status === 'completed'
    if (activeTab === 'failed') return p.status === 'failed'
    if (activeTab === 'pending') return p.status === 'pending'
    return true
  }).filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()))

  const counts = {
    all: projects.length,
    processing: projects.filter(p => p.status === 'processing').length,
    completed: projects.filter(p => p.status === 'completed').length,
    failed: projects.filter(p => p.status === 'failed').length,
    pending: projects.filter(p => p.status === 'pending').length,
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-mark">VC</div>
          <div className="sidebar-brand-name">视频切片工具</div>
        </div>

        <div className="sidebar-section-label">工作区</div>
        <button
          className={`nav-item ${location.pathname === '/' ? 'active' : ''}`}
          onClick={() => navigate('/')}
        >
          <span className="nav-item-icon">▶</span>
          切片项目
          <span className="nav-item-count">{projects.length}</span>
        </button>
        <button
          className={`nav-item ${location.pathname === '/styles' ? 'active' : ''}`}
          onClick={() => navigate('/styles')}
        >
          <span className="nav-item-icon">✎</span>
          风格管理
          <span className="nav-item-count">{customStyles.length}</span>
        </button>

        <div className="sidebar-bottom">
          <div className="user-chip">
            <div className="user-avatar">U</div>
            <div>
              <div className="user-name">工作台</div>
              <div className="user-status">● 在线</div>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div className="topbar-left">
            <span className="breadcrumb">
              <span>工作台</span>
              <span className="breadcrumb-sep">/</span>
              <span className="page-title">切片项目</span>
            </span>
          </div>
          <div className="topbar-right">
            <input
              className="search-input"
              type="text"
              placeholder="搜索项目..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <label className="btn btn-primary upload-compact">
              <span>⏵</span>
              <span>新建切片</span>
              <input type="file" accept="video/*" onChange={handleUpload} disabled={uploading} />
            </label>
            {uploading && (
              <UploadProgressBar
                state={uploadState}
                progress={uploadProgress}
                error={uploadError}
                onPause={handlePause}
                onResume={handleResume}
                onCancel={handleCancel}
              />
            )}
          </div>
        </div>

        <div className="content fade-in">
          <div className="content-header">
            <div>
              <div className="content-title">所有切片</div>
              <div className="content-subtitle">
                {projects.length} 个项目 · {uploading ? `上传中 ${uploadProgress}%` : '空闲'}
              </div>
            </div>
          </div>

          <div className="tabs">
            {[
              ['all', '全部'],
              ['processing', '处理中'],
              ['completed', '已完成'],
              ['pending', '待处理'],
              ['failed', '失败'],
            ].map(([k, label]) => (
              <button
                key={k}
                className={`tab ${activeTab === k ? 'active' : ''}`}
                onClick={() => setActiveTab(k)}
              >
                {label}
                <span className="tab-count">{counts[k]}</span>
              </button>
            ))}
          </div>

          {filteredProjects.length > 0 ? (
            <div className="reel-list">
              {filteredProjects.map(p => (
                <div
                  key={p.id}
                  className="reel-row"
                  data-status={p.status}
                  onClick={() => navigate(`/project/${p.id}`)}
                >
                  <div className="reel-status-dot" />
                  <div className="reel-name">{p.name}</div>
                  <span className="status-pill" data-status={p.status}>{statusLabel[p.status] || p.status}</span>
                  <div className="reel-cell">{formatTC(p.video_duration)}</div>
                  <div className="reel-cell">{p.clip_count || 0} 个切片</div>
                  <div className="reel-cell">{formatDate(p.created_at)}</div>
                  <div className="reel-actions" onClick={e => e.stopPropagation()}>
                    {p.status === 'pending' && (
                      <button className="btn btn-ghost btn-sm" onClick={() => startProcessing(p.id)}>▶ 处理</button>
                    )}
                    <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/project/${p.id}`)}>打开</button>
                    <button className="btn btn-ghost btn-sm btn-danger" onClick={() => deleteProject(p.id, p.name)}>✕</button>
                  </div>
                  {p.status === 'processing' && (
                    <div className="reel-progress-mini" style={{ gridColumn: '1 / -1', marginTop: 'var(--space-2)' }}>
                      <div className="reel-progress-mini-fill" style={{ width: `${p.progress || 0}%` }} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty">
              <div className="empty-icon">∅</div>
              <div className="empty-title">还没有切片项目</div>
              <div className="empty-hint">
                点击右上角 <b style={{ color: 'var(--accent)' }}>⏵ 新建切片</b> 上传第一个视频
              </div>
            </div>
          )}
        </div>
      </main>

      {showStrategyModal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <div className="modal-title">
                <div className="modal-title-icon" />
                选择处理策略
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => { setShowStrategyModal(false); setPendingProject(null) }}>✕</button>
            </div>

            <div className="modal-body">
              <div className="toggle-row">
                <div>
                  <div className="toggle-info-label" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                    烧录字幕到视频
                    <span style={{
                      fontSize: 'var(--text-xs)', color: 'var(--accent)',
                      background: 'var(--accent-soft)',
                      padding: '1px var(--space-2)', borderRadius: '999px',
                      fontWeight: 500
                    }}>
                      推荐开启
                    </span>
                  </div>
                  <div className="toggle-info-hint">关 = 纯剪（更快）· 开 = 带字幕（更慢，但传播力更强）</div>
                </div>
                <div
                  className={`toggle-switch ${withSubtitle ? 'on' : ''}`}
                  onClick={() => setWithSubtitle(!withSubtitle)}
                />
              </div>

              <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', fontFamily: 'var(--text-mono)', marginBottom: 'var(--space-3)' }}>
                预设策略
              </div>
              <div className="strategy-grid">
                {presets.map((p, i) => (
                  <button key={p.id} className="strategy-item" onClick={() => selectStrategy(p)}>
                    <div className="strategy-icon">{p.name.split(' ')[0]}</div>
                    <div className="strategy-body">
                      <div className="strategy-name">{p.name.split(' ').slice(1).join(' ') || p.name}</div>
                      <div className="strategy-desc">{p.description}</div>
                      <div className="strategy-meta">
                        <span>时长 <b>{p.target_duration}s</b></span>
                        <span>最多 <b>{p.max_clips}</b></span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>

              {customStyles.length > 0 && (
                <>
                  <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', fontFamily: 'var(--text-mono)', margin: 'var(--space-5) 0 var(--space-3)' }}>
                    自定义风格
                  </div>
                  <div className="strategy-grid">
                    {customStyles.map(s => (
                      <button key={s.id} className="strategy-item" onClick={() => selectStrategy(s)}>
                        <div className="strategy-icon">✎</div>
                        <div className="strategy-body">
                          <div className="strategy-name">{s.name}</div>
                          {s.description && <div className="strategy-desc">{s.description}</div>}
                          <div className="strategy-meta">
                            <span>时长 <b>{s.target_duration}s</b></span>
                            <span>最多 <b>{s.max_clips}</b></span>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => { setShowStrategyModal(false); setPendingProject(null) }}>取消</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function UploadProgressBar({ state, progress, error, onPause, onResume, onCancel }) {
  const { received, total, speed } = progress
  const pct = total > 0 ? Math.min(100, (received / total) * 100) : 0
  const remain = speed > 0 ? (total - received) / speed : null

  const stateLabel = {
    uploading: '上传中',
    resuming: '恢复中',
    pausing: '暂停中',
    paused: '已暂停',
    retrying: '重试中',
    finalizing: '合并中',
    done: '完成',
    error: '出错',
  }[state] || state

  return (
    <div className="upload-progress" style={{
      position: 'absolute', top: 'calc(100% + 8px)', right: 0,
      width: '420px', background: 'var(--bg-elevated)',
      border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)',
      padding: 'var(--space-4)', boxShadow: 'var(--shadow-md)',
      zIndex: 100
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2)' }}>
        <span style={{
          fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)',
          color: state === 'error' ? 'var(--danger)' : 'var(--accent)',
          fontWeight: 600
        }}>{stateLabel}</span>
        <span style={{ fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
          {formatBytes(received)} / {formatBytes(total)}
        </span>
      </div>

      {/* 进度条 */}
      <div style={{
        height: '8px', background: 'var(--bg-base)', borderRadius: '4px',
        overflow: 'hidden', marginBottom: 'var(--space-2)'
      }}>
        <div style={{
          width: `${pct}%`, height: '100%',
          background: state === 'error' ? 'var(--danger)' : 'var(--accent)',
          transition: 'width 0.2s ease-out'
        }} />
      </div>

      {/* 数字行 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)',
        color: 'var(--text-muted)', marginBottom: 'var(--space-3)'
      }}>
        <span>{pct.toFixed(1)}%</span>
        <span>{formatSpeed(speed)}</span>
        <span>剩余 {formatTime(remain)}</span>
      </div>

      {/* 网络慢提示（速度 < 200 KB/s 且已传 > 1MB） */}
      {received > 1024 * 1024 && speed > 0 && speed < 200 * 1024 && (
        <div style={{
          padding: 'var(--space-2) var(--space-3)', marginBottom: 'var(--space-3)',
          background: 'rgba(234, 179, 8, 0.1)', color: '#b45309',
          borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-xs)',
          border: '1px solid rgba(234, 179, 8, 0.3)'
        }}>
          ⚠️ 网络较慢（{formatSpeed(speed)}）。建议：本地用 ffmpeg 转 720p 再传，文件小 3-5 倍
        </div>
      )}

      {error && (
        <div style={{
          padding: 'var(--space-2) var(--space-3)', marginBottom: 'var(--space-3)',
          background: 'var(--danger-soft)', color: 'var(--danger)',
          borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-xs)'
        }}>
          {error}
        </div>
      )}

      {/* 控制按钮 */}
      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
        {state === 'uploading' && (
          <button className="btn btn-ghost btn-sm" onClick={onPause} style={{ flex: 1 }}>暂停</button>
        )}
        {state === 'paused' && (
          <button className="btn btn-primary btn-sm" onClick={onResume} style={{ flex: 1 }}>继续</button>
        )}
        {(state === 'uploading' || state === 'paused' || state === 'error') && (
          <button className="btn btn-ghost btn-sm btn-danger" onClick={onCancel} style={{ flex: 1 }}>取消</button>
        )}
        {state === 'finalizing' && (
          <span style={{ flex: 1, textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
            正在合并分片并创建项目…
          </span>
        )}
      </div>
    </div>
  )
}

export default App