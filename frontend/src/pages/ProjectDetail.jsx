import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import axios from 'axios'

const API_BASE = '/api/v1'

const statusLabel = {
  pending: '待处理',
  processing: '处理中',
  completed: '已完成',
  failed: '失败'
}

function formatTime(seconds) {
  if (seconds == null) return '--:--'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function formatDuration(seconds) {
  // 123 → "2 分 3 秒"; 3725 → "1 小时 2 分"; 45 → "45 秒"
  if (seconds == null) return '估算中...'
  if (seconds < 60) return `${Math.floor(seconds)} 秒`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h} 小时 ${m} 分`
  if (s > 0 && m < 5) return `${m} 分 ${s} 秒`
  return `${m} 分钟`
}

function formatTC(s) {
  if (!s) return '--:--'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

function formatSize(bytes) {
  if (!bytes) return '--'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function formatDate(iso) {
  if (!iso) return '--'
  return new Date(iso + 'Z').toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}

// ===== 错误信息友好化 =====
function friendlyError(taskError, projectStatus) {
  if (!taskError) return null
  const err = String(taskError).toLowerCase()

  // 常见错误模式匹配 + 给"怎么修"
  if (err.includes('moov atom') || err.includes('invalid data') || err.includes('exit status 183')) {
    return {
      title: '视频文件无法读取',
      hint: 'ffmpeg 找不到 moov atom——文件可能上传时被截断、或格式不被支持。建议：1) 重新上传 2) 用 ffmpeg 重新转一次 3) 检查文件大小是否正确',
    }
  }
  if (err.includes('ffmpeg') && err.includes('exit status')) {
    return {
      title: 'ffmpeg 处理失败',
      hint: 'ffmpeg 异常退出。可能是：1) 视频文件损坏 2) 磁盘空间满 3) 内存不足。建议：清理磁盘后重试',
    }
  }
  if (err.includes('whisper') || err.includes('cuda') || err.includes('out of memory')) {
    return {
      title: 'Whisper 转录失败',
      hint: '音频识别出错。可能是：1) 没有音频轨 2) 模型加载失败 3) 内存不足。建议：换个视频试试，或联系管理员',
    }
  }
  if (err.includes('database is locked') || err.includes('sqlite')) {
    return {
      title: '数据库被锁',
      hint: '多个 worker 同时写 SQLite 撞锁了。系统会自动重试，等 1-2 分钟刷新看',
    }
  }
  if (err.includes('timeout') || err.includes('time out')) {
    return {
      title: '处理超时',
      hint: '单步处理超时。可能是视频太大。建议：1) 切成小段再传 2) 调大 target_duration 让切片更少',
    }
  }
  return {
    title: '处理失败',
    hint: taskError.slice(0, 300),
  }
}

// ===== 桌面通知（封装：先请求权限） =====
async function notify(title, body) {
  if (!('Notification' in window)) return
  if (Notification.permission === 'default') {
    await Notification.requestPermission()
  }
  if (Notification.permission === 'granted') {
    try {
      new Notification(title, { body, icon: '/favicon.ico' })
    } catch (e) { /* 静默 */ }
  }
}

function ProjectDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('clips')
  const [customStylesCount, setCustomStylesCount] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 8
  // 跟踪状态变化用于发通知
  const lastStatusRef = useRef(null)
  const notifiedRef = useRef(new Set())  // 已通知过的 project id

  useEffect(() => {
    loadProject()
    loadSidebarCounts()
  }, [id])

  // 处理中：2 秒刷一次（看 task 进度）；其他状态 5 秒
  useEffect(() => {
    if (!project) return
    const isProcessing = project.status === 'processing' || project.task?.status === 'running'
    const interval = setInterval(loadProject, isProcessing ? 2000 : 5000)
    return () => clearInterval(interval)
  }, [project?.status, project?.task?.status])

  // 状态变化时发桌面通知
  useEffect(() => {
    if (!project) return
    const status = project.status
    const prev = lastStatusRef.current
    lastStatusRef.current = status

    // 处理中 → 完成：通知
    if (prev === 'processing' && status === 'completed' && !notifiedRef.current.has(project.id + ':done')) {
      notifiedRef.current.add(project.id + ':done')
      notify(
        '✅ 切片完成',
        `「${project.name}」处理完成，共 ${project.clips?.length || 0} 个片段`
      )
    }
    // 处理中 → 失败：通知
    if (prev === 'processing' && status === 'failed' && !notifiedRef.current.has(project.id + ':fail')) {
      notifiedRef.current.add(project.id + ':fail')
      const err = friendlyError(project.task?.error_message, status)
      notify('❌ 切片失败', `「${project.name}」处理失败：${err?.title || '未知错误'}`)
    }
  }, [project?.status])

  const loadProject = async () => {
    try {
      const res = await axios.get(`${API_BASE}/projects/${id}`)
      setProject(res.data.project)
    } catch (error) {
      console.error('加载项目失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadSidebarCounts = async () => {
    try {
      const [p, s] = await Promise.all([
        axios.get(`${API_BASE}/projects/`),
        axios.get(`${API_BASE}/styles`)
      ])
      // projects count not strictly needed but mirrors StyleManager pattern
      setCustomStylesCount(s.data.length)
    } catch (e) { /* silent */ }
  }

  const startProcessing = async () => {
    try {
      await axios.post(`${API_BASE}/projects/${id}/process`)
      loadProject()
    } catch (e) {
      alert('启动失败：' + (e.response?.data?.detail || e.message))
    }
  }

  const deleteProject = async () => {
    if (!confirm(`确定删除「${project.name}」？此操作不可恢复。`)) return
    try {
      await axios.delete(`${API_BASE}/projects/${id}`)
      navigate('/')
    } catch (e) {
      alert('删除失败：' + e.message)
    }
  }

  if (loading) {
    return (
      <div className="app-shell">
        <aside className="sidebar">
          <div className="sidebar-brand">
            <div className="sidebar-brand-mark">VC</div>
            <div className="sidebar-brand-name">视频切片工具</div>
          </div>
        </aside>
        <main className="main">
          <div className="topbar" />
          <div className="content">
            <div className="empty">
              <div className="empty-title">加载中...</div>
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="app-shell">
        <aside className="sidebar">
          <div className="sidebar-brand">
            <div className="sidebar-brand-mark">VC</div>
            <div className="sidebar-brand-name">视频切片工具</div>
          </div>
        </aside>
        <main className="main">
          <div className="topbar" />
          <div className="content">
            <div className="empty">
              <div className="empty-icon">∅</div>
              <div className="empty-title">项目不存在</div>
              <div className="empty-hint">它可能已被删除</div>
            </div>
          </div>
        </main>
      </div>
    )
  }

  const clips = project.clips || []
  const collections = project.collections || []
  const totalPages = Math.max(1, Math.ceil(clips.length / itemsPerPage))
  const pageClips = clips.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage)
  const hasBoth = clips.length > 0 && collections.length > 0
  const showTabs = clips.length > 0 || collections.length > 0

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-mark">VC</div>
          <div className="sidebar-brand-name">视频切片工具</div>
        </div>

        <div className="sidebar-section-label">工作区</div>
        <button className={`nav-item ${location.pathname === '/' ? 'active' : ''}`} onClick={() => navigate('/')}>
          <span className="nav-item-icon">▶</span>
          切片项目
          <span className="nav-item-count">—</span>
        </button>
        <button className={`nav-item ${location.pathname === '/styles' ? 'active' : ''}`} onClick={() => navigate('/styles')}>
          <span className="nav-item-icon">✎</span>
          风格管理
          <span className="nav-item-count">{customStylesCount}</span>
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
              <button className="btn btn-ghost btn-sm" onClick={() => navigate('/')}>← 返回</button>
              <span className="breadcrumb-sep">/</span>
              <span className="page-title" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 480 }}>
                {project.name}
              </span>
            </span>
          </div>
          <div className="topbar-right">
            {project.status === 'pending' && (
              <button className="btn btn-primary" onClick={startProcessing}>▶ 开始处理</button>
            )}
            <button className="btn btn-ghost btn-danger btn-sm" onClick={deleteProject}>✕ 删除</button>
          </div>
        </div>

        <div className="content fade-in">
          {/* === Project header card === */}
          <div className="content-header">
            <div>
              <div className="content-title" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                <span>{project.name}</span>
                <span className="status-pill" data-status={project.status}>{statusLabel[project.status] || project.status}</span>
              </div>
              <div className="content-subtitle">项目详情 · 共 {clips.length} 个切片 · {collections.length} 个合集</div>
            </div>
          </div>

          {/* === 实时进度（处理中显示） === */}
          {project.status === 'processing' && project.task && (
            <div style={{
              padding: 'var(--space-4)',
              background: 'var(--bg-elevated)',
              border: '1px solid var(--accent)',
              borderRadius: 'var(--radius-md)',
              marginBottom: 'var(--space-4)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-2)' }}>
                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--accent)' }}>
                  {project.task.current_step || '处理中...'}
                </span>
                <span style={{ fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                  {project.task.progress || 0}%
                </span>
              </div>
              <div style={{
                height: '8px', background: 'var(--bg-base)', borderRadius: '4px',
                overflow: 'hidden',
              }}>
                <div style={{
                  width: `${project.task.progress || 0}%`, height: '100%',
                  background: 'var(--accent)',
                  transition: 'width 0.3s ease-out',
                }} />
              </div>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                fontSize: 'var(--text-xs)', color: 'var(--text-dim)',
                marginTop: 'var(--space-3)', gap: 'var(--space-3)',
              }}>
                <span>
                  {project.task.elapsed_seconds != null && (
                    <>已用 <strong style={{ color: 'var(--text-secondary)' }}>{formatDuration(project.task.elapsed_seconds)}</strong></>
                  )}
                  {project.task.total_estimated_seconds != null && (
                    <> · 预计 <strong style={{ color: 'var(--text-secondary)' }}>{formatDuration(project.task.total_estimated_seconds)}</strong></>
                  )}
                </span>
                <span>
                  {project.task.eta_seconds != null ? (
                    <>剩余 <strong style={{ color: 'var(--accent)' }}>{formatDuration(project.task.eta_seconds)}</strong></>
                  ) : (
                    <em>估算中...</em>
                  )}
                </span>
              </div>
            </div>
          )}

          {/* === 错误卡片（友好提示） === */}
          {project.status === 'failed' && project.task?.error_message && (() => {
            const err = friendlyError(project.task.error_message, project.status)
            return (
              <div style={{
                padding: 'var(--space-4)',
                background: 'rgba(220, 38, 38, 0.05)',
                border: '1px solid rgba(220, 38, 38, 0.3)',
                borderRadius: 'var(--radius-md)',
                marginBottom: 'var(--space-4)',
              }}>
                <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
                  <span style={{ fontSize: 'var(--text-base)' }}>❌</span>
                  <div style={{ fontWeight: 600, color: 'var(--danger)' }}>{err?.title}</div>
                </div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                  {err?.hint}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: 'var(--space-3)', fontFamily: 'var(--text-mono)' }}>
                  原始错误：{project.task.error_message.slice(0, 200)}
                </div>
                <button className="btn btn-primary btn-sm" style={{ marginTop: 'var(--space-3)' }} onClick={startProcessing}>
                  🔄 重新处理
                </button>
              </div>
            )
          })()}

          {/* === Stat row (Linear-style meta) === */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 'var(--space-3)',
            marginBottom: 'var(--space-6)'
          }}>
            {[
              ['视频时长', formatTC(project.video_duration)],
              ['文件大小', formatSize(project.video_size)],
              ['切片数量', `${clips.length} 个`],
              ['合集数量', `${collections.length} 个`],
              ['创建时间', formatDate(project.created_at)],
              ['完成时间', project.completed_at ? formatDate(project.completed_at) : '—'],
            ].map(([label, value]) => (
              <div key={label} style={{
                padding: 'var(--space-4)',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)'
              }}>
                <div style={{
                  fontFamily: 'var(--text-mono)',
                  fontSize: 10,
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                  color: 'var(--text-dim)',
                  marginBottom: 'var(--space-2)'
                }}>
                  {label}
                </div>
                <div className="mono" style={{ fontSize: 'var(--text-md)', color: 'var(--text-bright)' }}>
                  {value}
                </div>
              </div>
            ))}
          </div>

          {/* === Tabs (clips / collections) === */}
          {showTabs && (
            <div className="tabs">
              {clips.length > 0 && (
                <button className={`tab ${activeTab === 'clips' ? 'active' : ''}`} onClick={() => { setActiveTab('clips'); setCurrentPage(1); }}>
                  切片视频
                  <span className="tab-count">{clips.length}</span>
                </button>
              )}
              {collections.length > 0 && (
                <button className={`tab ${activeTab === 'collections' ? 'active' : ''}`} onClick={() => { setActiveTab('collections'); setCurrentPage(1); }}>
                  合集视频
                  <span className="tab-count">{collections.length}</span>
                </button>
              )}
            </div>
          )}

          {/* === Clips grid === */}
          {activeTab === 'clips' && clips.length > 0 && (
            <div>
              {/* pagination header */}
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                marginBottom: 'var(--space-4)', color: 'var(--text-muted)', fontSize: 'var(--text-xs)'
              }}>
                <span className="mono">
                  显示 {((currentPage - 1) * itemsPerPage) + 1} - {Math.min(currentPage * itemsPerPage, clips.length)} / {clips.length} 个切片
                </span>
                <span className="mono">第 {currentPage} / {totalPages} 页</span>
              </div>

              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                gap: 'var(--space-4)'
              }}>
                {pageClips.map((clip, index) => (
                  <div key={clip.id || index} style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: 'var(--space-4)',
                    display: 'flex', flexDirection: 'column', gap: 'var(--space-3)'
                  }}>
                    <div style={{
                      fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-bright)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                    }} title={clip.title}>
                      {clip.title || `切片 ${index + 1}`}
                    </div>

                    <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                      <span style={{
                        fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)',
                        background: 'var(--bg-base)', color: 'var(--text-muted)',
                        padding: '2px var(--space-2)', borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border-subtle)'
                      }}>
                        ⏱ {formatTime(clip.start_time)} – {formatTime(clip.end_time)}
                      </span>
                      <span style={{
                        fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)',
                        background: 'var(--bg-base)', color: 'var(--text-muted)',
                        padding: '2px var(--space-2)', borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border-subtle)'
                      }}>
                        {clip.duration?.toFixed(1)} 秒
                      </span>
                      <span style={{
                        fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)',
                        background: 'var(--accent-soft)', color: 'var(--accent)',
                        padding: '2px var(--space-2)', borderRadius: 'var(--radius-sm)'
                      }}>
                        评分 {clip.score?.toFixed(2)}
                      </span>
                    </div>

                    <video
                      controls
                      style={{
                        width: '100%', maxHeight: 480, borderRadius: 'var(--radius-sm)',
                        background: '#000', objectFit: 'contain', display: 'block'
                      }}
                      src={`${API_BASE}/projects/${id}/files/${encodeURIComponent(clip.video_path)}`}
                    >
                      {/* 只在没烧录字幕时显示 <track>，避免双层字幕叠加（烧录+track） */}
                      {project.processing_config?.with_subtitle === false && (
                        <track
                          label="中文"
                          kind="subtitles"
                          srclang="zh"
                          src={`${API_BASE}/projects/${id}/files/${encodeURIComponent('metadata/input.srt')}`}
                          default
                        />
                      )}
                    </video>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-xs)' }}>
                      <a
                        href={`${API_BASE}/projects/${id}/files/${encodeURIComponent('metadata/input.srt')}`}
                        download={`${project.name}_字幕.srt`}
                        style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 500 }}
                      >
                        ↓ 下载字幕
                      </a>
                      <span style={{ color: 'var(--text-dim)' }}>若字幕未显示，请在播放器中手动加载</span>
                    </div>
                  </div>
                ))}
              </div>

              {/* page buttons */}
              {totalPages > 1 && (
                <div style={{
                  display: 'flex', justifyContent: 'center', gap: 'var(--space-2)',
                  marginTop: 'var(--space-6)'
                }}>
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    style={{ opacity: currentPage === 1 ? 0.4 : 1 }}
                  >
                    ← 上一页
                  </button>
                  {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                    <button
                      key={p}
                      className={`btn btn-sm ${currentPage === p ? 'btn-primary' : 'btn-ghost'}`}
                      onClick={() => setCurrentPage(p)}
                    >
                      {p}
                    </button>
                  ))}
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={currentPage >= totalPages}
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    style={{ opacity: currentPage >= totalPages ? 0.4 : 1 }}
                  >
                    下一页 →
                  </button>
                </div>
              )}
            </div>
          )}

          {/* === Collections grid === */}
          {activeTab === 'collections' && collections.length > 0 && (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
              gap: 'var(--space-4)'
            }}>
              {collections.map((coll, index) => (
                <div key={coll.id || index} style={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  padding: 'var(--space-4)',
                  display: 'flex', flexDirection: 'column', gap: 'var(--space-3)'
                }}>
                  <div style={{
                    fontSize: 'var(--text-md)', fontWeight: 600, color: 'var(--text-bright)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                  }} title={coll.title}>
                    {coll.title || `合集 ${index + 1}`}
                  </div>

                  <span style={{
                    fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)',
                    background: 'var(--bg-base)', color: 'var(--text-muted)',
                    padding: '2px var(--space-2)', borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    alignSelf: 'flex-start'
                  }}>
                    📦 包含 {coll.clip_count} 个切片
                  </span>

                  {coll.video_path ? (
                    <>
                      <video
                        controls
                        style={{
                          width: '100%', maxHeight: 480, borderRadius: 'var(--radius-sm)',
                          background: '#000', objectFit: 'contain', display: 'block'
                        }}
                        src={`${API_BASE}/projects/${id}/files/${encodeURIComponent(coll.video_path)}`}
                      />
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                        💡 合集视频暂不支持字幕
                      </div>
                    </>
                  ) : (
                    <div style={{
                      padding: 'var(--space-4)', textAlign: 'center',
                      background: 'rgba(235, 87, 87, 0.08)',
                      border: '1px solid rgba(235, 87, 87, 0.2)',
                      borderRadius: 'var(--radius-sm)',
                      color: 'var(--status-error)', fontSize: 'var(--text-sm)'
                    }}>
                      ⚠ 视频文件不存在（合集生成失败）
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* === Empty state === */}
          {!showTabs && (
            <div className="empty">
              <div className="empty-icon">∅</div>
              <div className="empty-title">暂无视频数据</div>
              <div className="empty-hint">
                {project.status === 'pending' && '项目就绪，点击右上角「▶ 开始处理」生成切片'}
                {project.status === 'processing' && '处理中，请稍候...'}
                {project.status === 'failed' && '处理失败，请检查日志或重新处理'}
                {project.status === 'completed' && '处理完成，但未生成任何切片'}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default ProjectDetail