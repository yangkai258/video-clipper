import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import './index.css'

function App() {
  const [projects, setProjects] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [showStrategyModal, setShowStrategyModal] = useState(false)
  const [pendingProject, setPendingProject] = useState(null)
  const [presets, setPresets] = useState([])
  const [customStyles, setCustomStyles] = useState([])
  const [withSubtitle, setWithSubtitle] = useState(false)
  const [currentTime, setCurrentTime] = useState(new Date())
  const navigate = useNavigate()

  const API_BASE = '/api/v1'
  const VERSION_LABEL = 'BUILD v1.0'
  const TC_FORMAT = (date) => {
    const pad = (n) => String(n).padStart(2, '0')
    return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  }

  // Live clock
  useEffect(() => {
    const id = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const loadProjects = async () => {
    try {
      const res = await axios.get(`${API_BASE}/projects/`)
      setProjects(res.data.projects)
    } catch (error) {
      console.error('Load failed:', error)
    }
  }

  const loadStrategies = async () => {
    try {
      const [presetsRes, stylesRes] = await Promise.all([
        axios.get(`${API_BASE}/strategies/presets`),
        axios.get(`${API_BASE}/styles`)
      ])
      setPresets(presetsRes.data.strategies)
      setCustomStyles(stylesRes.data)
    } catch (error) {
      console.error('Strategy load failed:', error)
    }
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
    const name = prompt('REEL NAME:', file.name.replace(/\.[^/.]+$/, ''))
    if (!name) return

    setUploading(true)
    setUploadProgress(0)

    const formData = new FormData()
    formData.append('name', name)
    formData.append('video', file)

    try {
      const res = await axios.post(`${API_BASE}/projects/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          setUploadProgress(Math.round((e.loaded * 100) / e.total))
        }
      })
      setPendingProject({ id: res.data.project_id, name })
      setShowStrategyModal(true)
      setUploading(false)
      loadProjects()
    } catch (error) {
      alert(`Upload failed: ${error.response?.data?.detail || error.message}`)
      setUploading(false)
    }
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
    } catch (error) {
      console.error('Config update failed:', error)
    }

    try {
      await axios.post(`${API_BASE}/projects/${pendingProject.id}/process`)
      loadProjects()
    } catch (error) {
      alert(`Process failed: ${error.response?.data?.detail || error.message}`)
    }
    setPendingProject(null)
  }

  const startProcessing = async (projectId) => {
    if (!confirm('Start processing this reel?')) return
    try {
      await axios.post(`${API_BASE}/projects/${projectId}/process`)
      loadProjects()
    } catch (error) {
      alert(`Failed: ${error.response?.data?.detail || error.message}`)
    }
  }

  const deleteProject = async (projectId, projectName) => {
    if (!confirm(`Delete "${projectName}"? This cannot be undone.`)) return
    try {
      await axios.delete(`${API_BASE}/projects/${projectId}`)
      loadProjects()
    } catch (error) {
      alert(`Delete failed: ${error.message}`)
    }
  }

  // Helpers
  const formatTimecode = (seconds) => {
    if (!seconds) return '00:00:00:00'
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    const f = Math.floor((seconds % 1) * 24)
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}:${String(f).padStart(2, '0')}`
  }

  const formatDate = (iso) => {
    if (!iso) return '--'
    return new Date(iso + 'Z').toLocaleString('zh-CN', {
      timeZone: 'Asia/Shanghai',
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit'
    })
  }

  const getStatusLabel = (status) => {
    const map = { pending: 'READY', processing: 'RENDERING', completed: 'DONE', failed: 'ERROR' }
    return map[status] || status.toUpperCase()
  }

  return (
    <>
      {/* === Top status bar (NLE-style) === */}
      <div className="status-bar">
        <div className="status-bar-left">
          <span className="status-brand">
            <span className="dot"></span>
            VIDEO CLIPPER
          </span>
          <span className="status-divider"></span>
          <span>{VERSION_LABEL}</span>
          <span className="status-divider"></span>
          <span>REELS: <span className="status-clock">{String(projects.length).padStart(3, '0')}</span></span>
        </div>
        <div className="status-bar-right">
          <span className="status-clock">{TC_FORMAT(currentTime)}</span>
          <span className="status-divider"></span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => navigate('/styles')}
            style={{ fontSize: 10 }}
          >
            ⚙ STYLES
          </button>
        </div>
      </div>

      <div className="container fade-in">
        {/* === Hero upload zone === */}
        <div className="hero-zone">
          <div className="hero-zone-icon">⏵</div>
          <div className="hero-title">Drop a reel to begin</div>
          <div className="hero-subtitle">MP4 · MOV · MKV · AVI · WEBM</div>
          <input
            type="file"
            accept="video/*"
            onChange={handleUpload}
            disabled={uploading}
          />
          {uploading && (
            <div className="hero-timecode">
              UPLOADING <span className="mono">{String(uploadProgress).padStart(3, '0')}%</span>
            </div>
          )}
        </div>

        {/* === Reels list === */}
        <div className="section-label">REELS / {projects.length}</div>

        {projects.length > 0 ? (
          <div className="timeline-row">
            {projects.map((p) => (
              <div
                key={p.id}
                className="reel-card"
                data-status={p.status}
                onClick={() => navigate(`/project/${p.id}`)}
              >
                <div className="reel-status-dot" title={getStatusLabel(p.status)}></div>
                <div className="reel-info">
                  <div className="reel-name">{p.name}</div>
                  <div className="reel-meta">
                    <span>{getStatusLabel(p.status)}</span>
                    <span className="reel-meta-divider"></span>
                    <span>{p.clip_count || 0} CLIPS</span>
                    <span className="reel-meta-divider"></span>
                    <span>{p.collection_count || 0} REELS</span>
                    <span className="reel-meta-divider"></span>
                    <span>{formatDate(p.created_at)}</span>
                  </div>
                </div>
                <div className="reel-actions" onClick={(e) => e.stopPropagation()}>
                  <span className="reel-tc">
                    <span className="tc-now">REC</span> · {p.video_duration ? formatTimecode(p.video_duration) : '--:--:--'}
                  </span>
                  {p.status === 'pending' && (
                    <button className="btn btn-primary btn-sm" onClick={() => startProcessing(p.id)}>
                      ▶ RENDER
                    </button>
                  )}
                  <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/project/${p.id}`)}>
                    OPEN
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => deleteProject(p.id, p.name)} style={{ color: 'var(--status-error)' }}>
                    ✕
                  </button>
                </div>
                {p.status === 'processing' && (
                  <div className="reel-progress">
                    <div className="reel-progress-fill" style={{ width: `${p.progress || 0}%` }}></div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <div style={{ fontSize: 48, opacity: 0.2 }}>∅</div>
            <div className="empty-state-title">NO REELS · DROP A VIDEO TO START</div>
          </div>
        )}

        {/* === Strategy selection modal === */}
        {showStrategyModal && (
          <div className="modal-overlay">
            <div className="modal-content">
              <div className="modal-header">
                <div className="modal-title">SELECT RENDER STRATEGY</div>
                <button className="btn btn-ghost btn-sm" onClick={() => { setShowStrategyModal(false); setPendingProject(null) }}>✕</button>
              </div>

              <div className="modal-body">
                <div className="toggle-row">
                  <div className="toggle-row-info">
                    <div className="toggle-row-label">BURN SUBTITLES INTO VIDEO</div>
                    <div className="toggle-row-hint">OFF: pure cut, faster · ON: subtitled, slower</div>
                  </div>
                  <div
                    className={`toggle-switch ${withSubtitle ? 'on' : ''}`}
                    onClick={() => setWithSubtitle(!withSubtitle)}
                    role="switch"
                    aria-checked={withSubtitle}
                  ></div>
                </div>

                <div className="section-label">PRESETS</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)', marginBottom: 'var(--space-5)' }}>
                  {presets.map((preset, idx) => (
                    <button
                      key={preset.id}
                      className="strategy-track"
                      onClick={() => selectStrategy(preset)}
                    >
                      <div className="strategy-track-id">
                        {String(idx + 1).padStart(2, '0')}
                      </div>
                      <div className="strategy-track-content">
                        <div className="strategy-track-name">{preset.name}</div>
                        <div className="strategy-track-desc">{preset.description}</div>
                        <div className="strategy-track-meta">
                          <span><span className="meta-key">DUR</span> <span className="meta-val">{preset.target_duration}s</span></span>
                          <span><span className="meta-key">MAX</span> <span className="meta-val">{preset.max_clips}</span></span>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>

                {customStyles.length > 0 && (
                  <>
                    <div className="section-label">CUSTOM STYLES / {customStyles.length}</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 'var(--space-2)' }}>
                      {customStyles.map((style, idx) => (
                        <button
                          key={style.id}
                          className="strategy-track"
                          onClick={() => selectStrategy(style)}
                        >
                          <div className="strategy-track-id">S{String(idx + 1).padStart(2, '0')}</div>
                          <div className="strategy-track-content">
                            <div className="strategy-track-name">{style.name}</div>
                            {style.description && (
                              <div className="strategy-track-desc">{style.description}</div>
                            )}
                            <div className="strategy-track-meta">
                              <span><span className="meta-key">DUR</span> <span className="meta-val">{style.target_duration}s</span></span>
                              <span><span className="meta-key">MAX</span> <span className="meta-val">{style.max_clips}</span></span>
                              {style.content_guidelines && (
                                <span style={{ color: 'var(--text-muted)' }}>
                                  · {style.content_guidelines.substring(0, 40)}{style.content_guidelines.length > 40 ? '...' : ''}
                                </span>
                              )}
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <div className="modal-footer">
                <button className="btn btn-ghost" onClick={() => { setShowStrategyModal(false); setPendingProject(null) }}>
                  CANCEL
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}

export default App