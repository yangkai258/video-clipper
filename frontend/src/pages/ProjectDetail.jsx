import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import axios from 'axios'

const API_BASE = '/api/v1'

const statusLabel = {
  pending: '待处理',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
  deleted: '已删除',
}

function formatTime(seconds) {
  if (!seconds) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function formatTC(s) {
  if (!s) return '00:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

// v2.1.26: 根据宽高判断视频 orientation (portrait/landscape/cinemascope/square)
function getOrientation(width, height) {
  if (!width || !height) return 'landscape'  // 默认横屏
  const ratio = width / height
  if (ratio < 0.83) return 'portrait'         // < 5:6 算竖屏 (9:16 = 0.5625)
  if (ratio >= 2.0) return 'cinemascope'      // >= 2:1 算宽银幕 (2.35:1)
  if (ratio > 1.2) return 'landscape'
  return 'square'
}

// 中文标签映射
const orientationLabel = {
  portrait: '竖屏',
  landscape: '横屏',
  cinemascope: '宽银幕',
  square: '方形',
}

function friendlyError(taskError) {
  if (!taskError) return { title: '处理失败', hint: '请查看日志或重新处理' }
  const err = String(taskError).toLowerCase()
  if (err.includes('ffmpeg') || err.includes('invalid data')) {
    return { title: '视频格式不支持', hint: 'ffmpeg 解析失败，请确认视频文件完整且格式标准' }
  }
  if (err.includes('memory') || err.includes('out of memory')) {
    return { title: '内存不足', hint: '视频可能过大，建议分段或降低分辨率' }
  }
  if (err.includes('timeout')) {
    return { title: '处理超时', hint: '请尝试较小的视频或重新处理' }
  }
  if (err.includes('whisper')) {
    return { title: '语音识别失败', hint: 'Whisper 加载或转录失败，请检查模型' }
  }
  return { title: '处理失败', hint: '请查看原始错误或重试' }
}

function notify(title, body) {
  if (!('Notification' in window)) return
  if (Notification.permission === 'granted') new Notification(title, { body })
}

// 懒加载视频卡: 默认只显示缩略图, 点 play 才挂载 video 标签
function ClipCard({ clip, index, projectId, withSubtitle }) {
  const [playing, setPlaying] = useState(false)
  const [errored, setErrored] = useState(false)
  const videoSrc = `${API_BASE}/projects/${projectId}/files/${encodeURIComponent(clip.video_path)}`
  const srtSrc = `${API_BASE}/projects/${projectId}/files/${encodeURIComponent('metadata/input.srt')}`
  // 用 clip 文件名派生缩略图 key
  const clipStem = clip.video_path ? clip.video_path.split('/').pop().replace(/\.mp4$/i, '') : null
  const thumbSrc = clipStem
    ? `/api/v1/clip-thumbs/${projectId}/${encodeURIComponent(clipStem)}.jpg`
    : `/api/v1/thumbnails/${projectId}.jpg`
  // v2.1.26: 按 orientation 选容器
  const orientation = getOrientation(clip.width, clip.height)
  return (
    <div className="pda-clip">
      <div className="pda-clip-thumb" data-orientation={orientation}>
        {playing ? (
          <video controls autoPlay className="pda-clip-video" src={videoSrc}>
            {!withSubtitle && (
              <track label="中文" kind="subtitles" srclang="zh" src={srtSrc} default />
            )}
          </video>
        ) : (
          <button className="pda-clip-poster" onClick={() => setPlaying(true)} title="点击播放">
            <img
              src={thumbSrc}
              alt={clip.title || `片段 ${index + 1}`}
              loading="lazy"
              onError={(e) => {
                if (!errored) { setErrored(true); e.currentTarget.src = `/api/v1/thumbnails/${projectId}.jpg` }
              }}
            />
            <div className="pda-clip-poster-overlay">
              <div className="pda-clip-play-btn">▶</div>
              <div className="pda-clip-duration">{(clip.duration || 0).toFixed(1)} 秒</div>
            </div>
          </button>
        )}
      </div>
      <div className="pda-clip-body">
        <div className="pda-clip-title" title={clip.title}>{clip.title || `片段 ${index + 1}`}</div>
        <div className="pda-clip-meta">
          <span className="mono">⏱ {formatTime(clip.start_time)} – {formatTime(clip.end_time)}</span>
          <span className="mono">⭐ {clip.score?.toFixed(2) || '—'}</span>
        </div>
      </div>
    </div>
  )
}

// 合集卡 (同懒加载)
function CollectionCard({ coll, index, projectId }) {
  const [playing, setPlaying] = useState(false)
  const videoSrc = coll.video_path
    ? `${API_BASE}/projects/${projectId}/files/${encodeURIComponent(coll.video_path)}`
    : null
  return (
    <div className="pda-clip">
      <div className="pda-clip-thumb">
        {!videoSrc ? (
          <div className="pda-clip-empty">⚠ 视频文件不存在</div>
        ) : playing ? (
          <video controls autoPlay className="pda-clip-video" src={videoSrc} />
        ) : (
          <button className="pda-clip-poster" onClick={() => setPlaying(true)} title="点击播放">
            <img
              src={`/api/v1/thumbnails/${projectId}.jpg`}
              alt={coll.title || `合集 ${index + 1}`}
              loading="lazy"
            />
            <div className="pda-clip-poster-overlay">
              <div className="pda-clip-play-btn">▶</div>
              <div className="pda-clip-duration">📦 {coll.clip_count} 切片</div>
            </div>
          </button>
        )}
      </div>
      <div className="pda-clip-body">
        <div className="pda-clip-title" title={coll.title}>{coll.title || `合集 ${index + 1}`}</div>
      </div>
    </div>
  )
}

export default function ProjectDetail({ projectId, navigate: navProp }) {
  const navigate = navProp || useNavigate()
  const id = projectId
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('clips')
  // 每个 tab 独立分页 (避免切到合集再切回切片被重置到第 1 页)
  // v2.1.27: page 用 URL search params 存 (绕过 React state 反复重置的 bug)
  // 即使 ProjectDetail 组件被反复 unmount/remount (Vite Fast Refresh / 路由变化), URL 还在
  const [searchParams, setSearchParams] = useSearchParams()
  const clipsPage = parseInt(searchParams.get('cp') || '1', 10)
  const collectionsPage = parseInt(searchParams.get('kp') || '1', 10)
  const setClipsPage = (p) => {
    const next = new URLSearchParams(searchParams)
    next.set('cp', String(p))
    setSearchParams(next, { replace: true })
  }
  const setCollectionsPage = (p) => {
    const next = new URLSearchParams(searchParams)
    next.set('kp', String(p))
    setSearchParams(next, { replace: true })
  }
  // v2.1.26: 必须放在所有 useEffect 之前! (否则违反 hooks 顺序规则, 会触发整体 unmount)
  const [updatingFormat, setUpdatingFormat] = useState(false)
  const itemsPerPage = 8
  const lastStatusRef = useRef(null)
  const notifiedRef = useRef(new Set())

  useEffect(() => {
    if (id) {
      loadProject()
      if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission()
    }
  }, [id])

  useEffect(() => {
    if (!project) return
    const isProcessing = project.status === 'processing' || project.task?.status === 'running'
    const interval = setInterval(loadProject, isProcessing ? 2000 : 5000)
    return () => clearInterval(interval)
  }, [project?.status, project?.task?.status])

  useEffect(() => {
    if (!project) return
    const status = project.status
    const prev = lastStatusRef.current
    lastStatusRef.current = status
    if (prev === 'processing' && status === 'completed' && !notifiedRef.current.has(project.id + ':done')) {
      notifiedRef.current.add(project.id + ':done')
      notify('✅ 切片完成', `「${project.name}」处理完成，共 ${project.clips?.length || 0} 个片段`)
    }
    if (prev === 'processing' && status === 'failed' && !notifiedRef.current.has(project.id + ':fail')) {
      notifiedRef.current.add(project.id + ':fail')
      const err = friendlyError(project.task?.error_message)
      notify('❌ 切片失败', `「${project.name}」处理失败：${err.title}`)
    }
  }, [project?.status])

  const loadProject = async () => {
    try {
      const res = await axios.get(`${API_BASE}/projects/${id}`)
      setProject(res.data.project)
    } catch (e) {
      console.error('加载项目失败:', e)
    } finally {
      setLoading(false)
    }
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
    if (!confirm(`确定删除「${project?.name}」？此操作不可恢复。`)) return
    try {
      await axios.delete(`${API_BASE}/projects/${id}`)
      navigate('/')
    } catch (e) {
      alert('删除失败：' + e.message)
    }
  }

  // v2.1.26: 改 output_format (后端更新 processing_config.output_format, 不重处理)
  // useState 在 useEffect 之前已定义 (line 174, 顺序约束)
  const updateOutputFormat = async (format) => {
    if (!confirm(`改输出格式为 "${format}", 会影响下次处理。\n\n已有 clip 不会被重新编码,只有重新处理才会用新格式。要现在重处理吗?`)) {
      // 用户说不要, 只更新 config
      try {
        setUpdatingFormat(true)
        await axios.put(`${API_BASE}/projects/${id}/config`, {
          ...project.processing_config,
          output_format: format,
        })
        loadProject()
      } catch (e) {
        alert('更新失败：' + (e.response?.data?.detail || e.message))
      } finally {
        setUpdatingFormat(false)
      }
    }
  }

  if (loading) {
    return (
      <div className="empty">
        <div className="empty-icon">⏳</div>
        <div className="empty-title">加载中...</div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="empty">
        <div className="empty-icon">∅</div>
        <div className="empty-title">项目不存在</div>
        <div className="empty-hint">它可能已被删除</div>
        <button className="btn btn-primary" style={{ marginTop: 'var(--space-3)' }} onClick={() => navigate('/')}>返回列表</button>
      </div>
    )
  }

  const clips = project.clips || []
  const collections = project.collections || []
  // 当前 tab 的分页 (切片/合集各持一份, 切 tab 互不干扰)
  const currentPage = activeTab === 'collections' ? collectionsPage : clipsPage
  const setCurrentPage = activeTab === 'collections' ? setCollectionsPage : setClipsPage
  const totalPages = Math.max(1, Math.ceil(clips.length / itemsPerPage))
  const pageClips = clips.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage)
  const showTabs = clips.length > 0 || collections.length > 0
  const task = project.task
  const cfg = project.processing_config || {}
  const isProcessing = project.status === 'processing'

  // 衍生指标
  const avgClipDuration = clips.length > 0 ? (clips.reduce((a, c) => a + (c.duration || 0), 0) / clips.length) : 0
  const avgScore = clips.length > 0 ? (clips.reduce((a, c) => a + (c.score || 0), 0) / clips.length) : 0
  const elapsed = (task?.started_at && (task?.completed_at || task?.failed_at)) ?
    (new Date(task.completed_at || task.failed_at) - new Date(task.started_at)) / 1000 : null
  const elapsedStr = elapsed ? `${Math.round(elapsed / 60)} 分钟` : '—'

  return (
    <div className="pda-layout">
      {/* === 顶部: 封面 + 标题 + actions === */}
      <div className="pda-header">
        {(() => {
          // v2.1.26: 按 orientation 选 cover class
          const orientation = getOrientation(project.video_width, project.video_height)
          const coverClass = `pda-cover pda-cover-${orientation}`
          return project.status === 'completed' ? (
            <div className={coverClass} title={`${orientationLabel[orientation] || ''} ${project.video_width || '?'}×${project.video_height || '?'}`}>
              <img
                className="pda-cover-img"
                src={`/api/v1/thumbnails/${id}.jpg`}
                alt={project.name}
                onError={(e) => { e.currentTarget.style.display = 'none' }}
              />
              <div className="pda-cover-play">▶</div>
            </div>
          ) : (
            <div className={`${coverClass} pda-cover-placeholder`} title={`${orientationLabel[orientation] || ''} ${project.video_width || '?'}×${project.video_height || '?'}`}>
              <div className="pda-cover-icon">
                {isProcessing ? '⏳' : project.status === 'failed' ? '❌' : '🎬'}
              </div>
            </div>
          )
        })()}
        <div className="pda-info">
          <div className="pda-info-top">
            <span className="status-pill" data-status={project.status}>{statusLabel[project.status] || project.status}</span>
          </div>
          <h1 className="pda-title">{project.name}</h1>
          <div className="pda-meta">
            <span>⏱ {formatTC(project.video_duration)}</span>
            <span className="pda-meta-sep">·</span>
            <span>📁 {project.video_size ? `${(project.video_size / 1024 / 1024).toFixed(1)} MB` : '—'}</span>
            <span className="pda-meta-sep">·</span>
            <span>📅 {formatDate(project.created_at)}</span>
          </div>
          <div className="pda-actions">
            {project.status === 'pending' && (
              <button className="btn btn-primary" onClick={startProcessing}>▶ 开始处理</button>
            )}
            {project.status === 'completed' && (
              <button className="btn btn-primary">▶ 播放预览</button>
            )}
            <button className="btn btn-ghost btn-sm">⏬ 下载 SRT</button>
            <button className="btn btn-ghost btn-sm btn-danger" onClick={deleteProject}>✕ 删除</button>
          </div>
        </div>
      </div>

      {/* === 4 列 metric 行 === */}
      <div className="pda-metrics">
        <div className="pda-metric">
          <div className="pda-metric-label">切片</div>
          <div className="pda-metric-value">{clips.length}</div>
        </div>
        <div className="pda-metric">
          <div className="pda-metric-label">合集</div>
          <div className="pda-metric-value">{collections.length}</div>
        </div>
        <div className="pda-metric">
          <div className="pda-metric-label">平均时长</div>
          <div className="pda-metric-value">
            {avgClipDuration > 0 ? avgClipDuration.toFixed(1) : '—'}
            <span className="pda-metric-unit"> 秒</span>
          </div>
        </div>
        <div className="pda-metric">
          <div className="pda-metric-label">平均分</div>
          <div className="pda-metric-value">
            {avgScore > 0 ? avgScore.toFixed(2) : '—'}
          </div>
        </div>
      </div>

      {/* === 处理中进度卡 (插在 metric 行下方) === */}
      {isProcessing && task && (
        <div className="pda-progress-card">
          <div className="pda-progress-step">{task.current_step || '处理中...'}</div>
          <div className="pda-progress">
            <div className="pda-progress-bar">
              <div className="pda-progress-fill" style={{ width: `${task.progress || 0}%` }} />
            </div>
            <span className="pda-progress-label">{task.progress || 0}%</span>
          </div>
          <div className="pda-progress-timing">
            {task.elapsed_seconds != null && <span>已用 <strong>{Math.round(task.elapsed_seconds / 60)} 分钟</strong></span>}
            {task.eta_seconds != null && <span>剩余 <strong>{Math.round(task.eta_seconds / 60)} 分钟</strong></span>}
            {task.total_estimated_seconds != null && <span>预计共 <strong>{Math.round(task.total_estimated_seconds / 60)} 分钟</strong></span>}
          </div>
        </div>
      )}

      {/* === 失败错误卡 === */}
      {project.status === 'failed' && task?.error_message && (
        <div className="pda-error-card">
          <div className="pda-error-title">❌ {friendlyError(task.error_message).title}</div>
          <div className="pda-error-hint">{friendlyError(task.error_message).hint}</div>
          <details className="pda-error-detail">
            <summary>查看原始错误</summary>
            <code>{task.error_message.slice(0, 400)}</code>
          </details>
          <button className="btn btn-primary btn-sm" style={{ marginTop: 'var(--space-3)' }} onClick={startProcessing}>🔄 重新处理</button>
        </div>
      )}

      {/* === 2 列: 左 tabs+grid, 右 2 张卡 === */}
      <div className="pda-body">
        <div className="pda-main">
          {showTabs ? (
            <>
              <div className="pda-tabs">
                {clips.length > 0 && (
                  <button className={`pda-tab ${activeTab === 'clips' ? 'active' : ''}`} onClick={() => setActiveTab('clips')}>
                    切片 <span className="pda-tab-count">{clips.length}</span>
                  </button>
                )}
                {collections.length > 0 && (
                  <button className={`pda-tab ${activeTab === 'collections' ? 'active' : ''}`} onClick={() => setActiveTab('collections')}>
                    合集 <span className="pda-tab-count">{collections.length}</span>
                  </button>
                )}
                <button className={`pda-tab ${activeTab === 'srt' ? 'active' : ''}`} onClick={() => setActiveTab('srt')}>字幕</button>
                <button className={`pda-tab ${activeTab === 'settings' ? 'active' : ''}`} onClick={() => setActiveTab('settings')}>设置</button>
              </div>

              {activeTab === 'clips' && clips.length > 0 && (
                <>
                  <div className="pda-grid-header">
                    <span>显示 {((currentPage - 1) * itemsPerPage) + 1} - {Math.min(currentPage * itemsPerPage, clips.length)} / {clips.length}</span>
                    <span>第 {currentPage} / {totalPages} 页</span>
                  </div>
                  <div className="pda-grid">
                    {pageClips.map((clip, i) => (
                      <ClipCard
                        key={clip.id || i}
                        clip={clip}
                        index={i}
                        projectId={id}
                        withSubtitle={cfg.with_subtitle !== false}
                      />
                    ))}
                  </div>
                  {totalPages > 1 && (
                    <div className="pda-pagination">
                      <button className="btn btn-ghost btn-sm" disabled={currentPage === 1} onClick={() => setCurrentPage(p => Math.max(1, p - 1))} style={{ opacity: currentPage === 1 ? 0.4 : 1 }}>← 上一页</button>
                      {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                        <button key={p} className={`btn btn-sm ${currentPage === p ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setCurrentPage(p)}>{p}</button>
                      ))}
                      <button className="btn btn-ghost btn-sm" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} style={{ opacity: currentPage >= totalPages ? 0.4 : 1 }}>下一页 →</button>
                    </div>
                  )}
                </>
              )}

              {activeTab === 'collections' && collections.length > 0 && (
                <div className="pda-grid">
                  {collections.map((coll, i) => (
                    <CollectionCard key={coll.id || i} coll={coll} index={i} projectId={id} />
                  ))}
                </div>
              )}

              {activeTab === 'srt' && (
                <div className="pda-srt">
                  <div className="pda-srt-info">
                    <div>📝 字幕文件 (SRT)</div>
                    <a className="btn btn-primary btn-sm" href={`${API_BASE}/projects/${id}/files/${encodeURIComponent('metadata/input.srt')}`} download={`${project.name}_字幕.srt`}>⏬ 下载 SRT</a>
                  </div>
                  <pre className="pda-srt-preview">（字幕预览待加载）</pre>
                </div>
              )}

              {activeTab === 'settings' && (
                <div className="pda-settings">
                  <div className="pda-setting-row"><span>风格</span><strong>{project.style_name || '默认'}</strong></div>
                  <div className="pda-setting-row"><span>目标时长</span><strong>{cfg.target_duration ? `${cfg.target_duration} 秒/片` : '—'}</strong></div>
                  <div className="pda-setting-row"><span>最大切片</span><strong>{cfg.max_clips ? `≤ ${cfg.max_clips} 片` : '—'}</strong></div>
                  <div className="pda-setting-row"><span>字幕</span><strong>{cfg.with_subtitle !== false ? '烧录到视频' : '不烧录'}</strong></div>
                  <div className="pda-setting-row"><span>处理策略</span><strong>{cfg.processing_mode || 'standard'}</strong></div>
                  {/* v2.1.26: 输出格式选项 (横屏电影 → 9:16 letterbox 等) */}
                  <div className="pda-setting-row">
                    <span>输出格式</span>
                    <strong style={{ color: cfg.output_format && cfg.output_format !== 'original' ? '#06b6d4' : undefined }}>
                      {cfg.output_format === '9:16-letterbox' ? '📱 9:16 上下黑边 (抖音适配)' : cfg.output_format === '9:16-smart-crop' ? '📱 9:16 智能裁剪 (TODO)' : '🎬 保持原比例'}
                    </strong>
                  </div>
                  {project.video_width && project.video_height && (
                    <div className="pda-setting-row">
                      <span>视频尺寸</span>
                      <strong>{project.video_width}×{project.video_height} ({orientationLabel[getOrientation(project.video_width, project.video_height)]})</strong>
                    </div>
                  )}
                  <div className="pda-setting-row" style={{ marginTop: '12px' }}>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => updateOutputFormat('original')}
                      disabled={updatingFormat || cfg.output_format === 'original'}
                    >
                      🎬 保持原比例
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => updateOutputFormat('9:16-letterbox')}
                      disabled={updatingFormat || cfg.output_format === '9:16-letterbox'}
                      style={{ marginLeft: '8px' }}
                    >
                      📱 转 9:16 (letterbox)
                    </button>
                  </div>
                  {(cfg.output_format === '9:16-letterbox') && (
                    <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
                      💡 横屏视频会被上下加黑边变成 9:16 (适合抖音);竖屏视频保持不变
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="empty">
              <div className="empty-icon">{isProcessing ? '⏳' : project.status === 'failed' ? '❌' : '∅'}</div>
              <div className="empty-title">
                {isProcessing ? '处理中，请稍候...' : project.status === 'pending' ? '项目就绪' : project.status === 'failed' ? '处理失败' : '暂无视频数据'}
              </div>
              <div className="empty-hint">
                {project.status === 'pending' && '点击顶部「▶ 开始处理」生成切片'}
                {project.status === 'failed' && '请检查日志或重新处理'}
              </div>
            </div>
          )}
        </div>

        <aside className="pda-side">
          <div className="pda-side-card">
            <div className="pda-side-label">处理信息</div>
            <dl className="pda-dl">
              <dt>风格</dt><dd>{project.style_name || '默认'}</dd>
              <dt>目标时长</dt><dd>{cfg.target_duration ? `${cfg.target_duration} 秒/片` : '—'}</dd>
              <dt>最大切片</dt><dd>{cfg.max_clips ? `≤ ${cfg.max_clips} 片` : '—'}</dd>
              <dt>字幕</dt><dd>{cfg.with_subtitle !== false ? '开启' : '关闭'}</dd>
            </dl>
          </div>
          <div className="pda-side-card">
            <div className="pda-side-label">时间</div>
            <dl className="pda-dl">
              <dt>创建</dt><dd>{formatDate(project.created_at)}</dd>
              <dt>开始</dt><dd>{formatDate(task?.started_at) || '—'}</dd>
              <dt>完成</dt><dd>{formatDate(project.completed_at) || '—'}</dd>
              <dt>耗时</dt><dd>{elapsedStr}</dd>
            </dl>
          </div>
        </aside>
      </div>
    </div>
  )
}
