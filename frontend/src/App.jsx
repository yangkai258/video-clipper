import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
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
      console.error('Load failed:', e)
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
    const name = prompt('Reel name:', file.name.replace(/\.[^/.]+$/, ''))
    if (!name) return
    setUploading(true)
    setUploadProgress(0)
    const formData = new FormData()
    formData.append('name', name)
    formData.append('video', file)
    try {
      const res = await axios.post(`${API_BASE}/projects/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => setUploadProgress(Math.round((e.loaded * 100) / e.total))
      })
      setPendingProject({ id: res.data.project_id, name })
      setShowStrategyModal(true)
      setUploading(false)
      loadProjects()
    } catch (e) {
      alert(`Upload failed: ${e.response?.data?.detail || e.message}`)
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
    } catch (e) { console.error('Config failed:', e) }

    try {
      await axios.post(`${API_BASE}/projects/${pendingProject.id}/process`)
      loadProjects()
    } catch (e) {
      alert(`Process failed: ${e.response?.data?.detail || e.message}`)
    }
    setPendingProject(null)
  }

  const startProcessing = async (id) => {
    try {
      await axios.post(`${API_BASE}/projects/${id}/process`)
      loadProjects()
    } catch (e) {
      alert(`Failed: ${e.response?.data?.detail || e.message}`)
    }
  }

  const deleteProject = async (id, name) => {
    if (!confirm(`Delete "${name}"?`)) return
    try {
      await axios.delete(`${API_BASE}/projects/${id}`)
      loadProjects()
    } catch (e) { alert(`Delete failed: ${e.message}`) }
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
      {/* === Sidebar === */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-mark">VC</div>
          <div className="sidebar-brand-name">Video Clipper</div>
        </div>

        <div className="sidebar-section-label">Workspace</div>
        <button
          className={`nav-item ${location.pathname === '/' ? 'active' : ''}`}
          onClick={() => navigate('/')}
        >
          <span className="nav-item-icon">▶</span>
          Reels
          <span className="nav-item-count">{projects.length}</span>
        </button>
        <button
          className={`nav-item ${location.pathname === '/styles' ? 'active' : ''}`}
          onClick={() => navigate('/styles')}
        >
          <span className="nav-item-icon">✎</span>
          Styles
          <span className="nav-item-count">{customStyles.length}</span>
        </button>

        <div className="sidebar-bottom">
          <div className="user-chip">
            <div className="user-avatar">U</div>
            <div>
              <div className="user-name">Studio</div>
              <div className="user-status">● Online</div>
            </div>
          </div>
        </div>
      </aside>

      {/* === Main === */}
      <main className="main">
        {/* Topbar */}
        <div className="topbar">
          <div className="topbar-left">
            <span className="breadcrumb">
              <span>Studio</span>
              <span className="breadcrumb-sep">/</span>
              <span className="page-title">Reels</span>
            </span>
          </div>
          <div className="topbar-right">
            <input
              className="search-input"
              type="text"
              placeholder="Search reels…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <label className="btn btn-primary upload-compact">
              <span>⏵</span>
              <span>New Reel</span>
              <input type="file" accept="video/*" onChange={handleUpload} disabled={uploading} />
            </label>
          </div>
        </div>

        <div className="content fade-in">
          <div className="content-header">
            <div>
              <div className="content-title">All Reels</div>
              <div className="content-subtitle">{projects.length} total · {uploading ? `uploading ${uploadProgress}%` : 'idle'}</div>
            </div>
          </div>

          {/* Tabs */}
          <div className="tabs">
            {[
              ['all', 'All'],
              ['processing', 'Processing'],
              ['completed', 'Completed'],
              ['pending', 'Pending'],
              ['failed', 'Failed'],
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

          {/* Reel list */}
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
                  <span className={`status-pill`} data-status={p.status}>{p.status}</span>
                  <div className="reel-cell">{formatTC(p.video_duration)}</div>
                  <div className="reel-cell">{p.clip_count || 0} clips</div>
                  <div className="reel-cell">{formatDate(p.created_at)}</div>
                  <div className="reel-actions" onClick={e => e.stopPropagation()}>
                    {p.status === 'pending' && (
                      <button className="btn btn-ghost btn-sm" onClick={() => startProcessing(p.id)}>▶</button>
                    )}
                    <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/project/${p.id}`)}>Open</button>
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
              <div className="empty-title">No reels yet</div>
              <div className="empty-hint">Click <b style={{ color: 'var(--accent)' }}>⏵ New Reel</b> in the top right to upload your first video</div>
            </div>
          )}
        </div>
      </main>

      {/* === Strategy modal === */}
      {showStrategyModal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <div className="modal-title">
                <div className="modal-title-icon" />
                Choose render strategy
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => { setShowStrategyModal(false); setPendingProject(null) }}>✕</button>
            </div>

            <div className="modal-body">
              <div className="toggle-row">
                <div>
                  <div className="toggle-info-label">Burn subtitles into video</div>
                  <div className="toggle-info-hint">Off = pure cut, faster · On = subtitled, slower</div>
                </div>
                <div
                  className={`toggle-switch ${withSubtitle ? 'on' : ''}`}
                  onClick={() => setWithSubtitle(!withSubtitle)}
                />
              </div>

              <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', fontFamily: 'var(--text-mono)', marginBottom: 'var(--space-3)' }}>
                Presets
              </div>
              <div className="strategy-grid">
                {presets.map((p, i) => (
                  <button key={p.id} className="strategy-item" onClick={() => selectStrategy(p)}>
                    <div className="strategy-icon">{p.name.split(' ')[0]}</div>
                    <div className="strategy-body">
                      <div className="strategy-name">{p.name.split(' ').slice(1).join(' ') || p.name}</div>
                      <div className="strategy-desc">{p.description}</div>
                      <div className="strategy-meta">
                        <span>DUR <b>{p.target_duration}s</b></span>
                        <span>MAX <b>{p.max_clips}</b></span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>

              {customStyles.length > 0 && (
                <>
                  <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', fontFamily: 'var(--text-mono)', margin: 'var(--space-5) 0 var(--space-3)' }}>
                    Custom styles
                  </div>
                  <div className="strategy-grid">
                    {customStyles.map(s => (
                      <button key={s.id} className="strategy-item" onClick={() => selectStrategy(s)}>
                        <div className="strategy-icon">✎</div>
                        <div className="strategy-body">
                          <div className="strategy-name">{s.name}</div>
                          {s.description && <div className="strategy-desc">{s.description}</div>}
                          <div className="strategy-meta">
                            <span>DUR <b>{s.target_duration}s</b></span>
                            <span>MAX <b>{s.max_clips}</b></span>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => { setShowStrategyModal(false); setPendingProject(null) }}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App