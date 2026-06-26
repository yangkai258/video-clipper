import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import axios from 'axios'

const API_BASE = '/api/v1'

const defaultStyle = {
  name: '',
  description: '',
  target_duration: 60,
  max_clips: 20,
  content_types: [],
  rules: { min_score: 0.7, priority_keywords: [] },
  content_guidelines: '',
  keep_rules: '',
  remove_rules: '',
  style_positioning: '',
  subtitle_config: {
    font_size: 22,
    txt_color: 'white',
    stroke_color: 'white',
    stroke_width: 1,
    font: 'Arial',
    position: 0.33
  }
}

function StyleManager() {
  const [styles, setStyles] = useState([])
  const [presets, setPresets] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(defaultStyle)
  const [tab, setTab] = useState('basic')
  const navigate = useNavigate()
  const location = useLocation()

  const loadStyles = async () => {
    try {
      const res = await axios.get(`${API_BASE}/styles`)
      setStyles(res.data)
    } catch (e) { console.error(e) }
  }

  const loadPresets = async () => {
    try {
      const res = await axios.get(`${API_BASE}/strategies/presets`)
      setPresets(res.data.strategies)
    } catch (e) { console.error(e) }
  }

  useEffect(() => {
    loadStyles()
    loadPresets()
  }, [])

  const openCreate = () => {
    setEditing(null)
    setForm(defaultStyle)
    setTab('basic')
    setShowModal(true)
  }

  const openEdit = (style) => {
    setEditing(style)
    setForm({
      ...style,
      content_types: style.content_types || [],
      rules: style.rules || { min_score: 0.7, priority_keywords: [] },
      subtitle_config: style.subtitle_config || defaultStyle.subtitle_config
    })
    setTab('basic')
    setShowModal(true)
  }

  const save = async () => {
    try {
      if (editing) {
        await axios.put(`${API_BASE}/styles/${editing.id}`, form)
      } else {
        await axios.post(`${API_BASE}/styles`, form)
      }
      setShowModal(false)
      loadStyles()
    } catch (e) {
      alert(`Save failed: ${e.response?.data?.detail || e.message}`)
    }
  }

  const remove = async (id, name) => {
    if (!confirm(`Delete "${name}"?`)) return
    try {
      await axios.delete(`${API_BASE}/styles/${id}`)
      loadStyles()
    } catch (e) { alert(`Delete failed: ${e.message}`) }
  }

  const applyPreset = (preset) => {
    setForm({
      ...form,
      name: preset.name.split(' ').slice(1).join(' '),
      description: preset.description,
      target_duration: preset.target_duration,
      max_clips: preset.max_clips,
      content_types: preset.content_types,
      rules: preset.rules,
      subtitle_config: defaultStyle.subtitle_config
    })
  }

  const update = (k, v) => setForm(prev => ({ ...prev, [k]: v }))
  const updateRule = (k, v) => setForm(prev => ({ ...prev, rules: { ...prev.rules, [k]: v } }))
  const updateSub = (k, v) => setForm(prev => ({ ...prev, subtitle_config: { ...prev.subtitle_config, [k]: v } }))

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-mark">VC</div>
          <div className="sidebar-brand-name">Video Clipper</div>
        </div>
        <div className="sidebar-section-label">Workspace</div>
        <button className={`nav-item ${location.pathname === '/' ? 'active' : ''}`} onClick={() => navigate('/')}>
          <span className="nav-item-icon">▶</span>
          Reels
          <span className="nav-item-count">—</span>
        </button>
        <button className={`nav-item ${location.pathname === '/styles' ? 'active' : ''}`} onClick={() => navigate('/styles')}>
          <span className="nav-item-icon">✎</span>
          Styles
          <span className="nav-item-count">{styles.length}</span>
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

      <main className="main">
        <div className="topbar">
          <div className="topbar-left">
            <span className="breadcrumb">
              <span>Studio</span>
              <span className="breadcrumb-sep">/</span>
              <span className="page-title">Styles</span>
            </span>
          </div>
          <div className="topbar-right">
            <button className="btn btn-primary" onClick={openCreate}>+ New Style</button>
          </div>
        </div>

        <div className="content fade-in">
          <div className="content-header">
            <div>
              <div className="content-title">Custom Styles</div>
              <div className="content-subtitle">{styles.length} configured · editorial voices for AI slicing</div>
            </div>
          </div>

          {presets.length > 0 && (
            <>
              <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', fontFamily: 'var(--text-mono)', marginBottom: 'var(--space-3)' }}>
                Quick start from preset
              </div>
              <div className="style-list" style={{ marginBottom: 'var(--space-6)' }}>
                {presets.map(p => (
                  <div key={p.id} className="style-item">
                    <div className="style-item-icon">{p.name.split(' ')[0]}</div>
                    <div className="style-item-body">
                      <div className="style-item-name">{p.name.split(' ').slice(1).join(' ') || p.name}</div>
                      <div className="style-item-desc">{p.description}</div>
                    </div>
                    <div className="style-item-meta">
                      <span>DUR <b style={{ color: 'var(--text-default)' }}>{p.target_duration}s</b></span>
                      <span>MAX <b style={{ color: 'var(--text-default)' }}>{p.max_clips}</b></span>
                    </div>
                    <div className="style-item-actions">
                      <button className="btn btn-ghost btn-sm" onClick={() => { applyPreset(p); openCreate(); }}>Use</button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', fontFamily: 'var(--text-mono)', marginBottom: 'var(--space-3)' }}>
            Your styles / {styles.length}
          </div>

          {styles.length > 0 ? (
            <div className="style-list">
              {styles.map(s => (
                <div key={s.id} className="style-item">
                  <div className="style-item-icon">✎</div>
                  <div className="style-item-body">
                    <div className="style-item-name">{s.name}</div>
                    {s.description && <div className="style-item-desc">{s.description}</div>}
                    {s.style_positioning && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)', marginTop: 'var(--space-1)' }}>
                        {s.style_positioning}
                      </div>
                    )}
                  </div>
                  <div className="style-item-meta">
                    <span>DUR <b style={{ color: 'var(--text-default)' }}>{s.target_duration}s</b></span>
                    <span>MAX <b style={{ color: 'var(--text-default)' }}>{s.max_clips}</b></span>
                  </div>
                  <div className="style-item-actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => openEdit(s)}>Edit</button>
                    <button className="btn btn-ghost btn-sm btn-danger" onClick={() => remove(s.id, s.name)}>✕</button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty">
              <div className="empty-icon">∅</div>
              <div className="empty-title">No custom styles</div>
              <div className="empty-hint">Create one or use a preset above</div>
            </div>
          )}
        </div>
      </main>

      {showModal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <div className="modal-title">
                <div className="modal-title-icon" />
                {editing ? `Edit · ${editing.name}` : 'New style'}
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowModal(false)}>✕</button>
            </div>

            <div className="tabs" style={{ paddingLeft: 'var(--space-6)' }}>
              {[['basic', 'Basic'], ['voice', 'Voice'], ['position', 'Positioning'], ['subtitle', 'Subtitle']].map(([k, label]) => (
                <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>
              ))}
            </div>

            <div className="modal-body">
              {tab === 'basic' && (
                <>
                  <div className="form-group">
                    <label>Name *</label>
                    <input type="text" value={form.name} onChange={e => update('name', e.target.value)} placeholder="e.g. ZOU_LIVESTREAM" />
                  </div>
                  <div className="form-group">
                    <label>Description</label>
                    <textarea value={form.description} onChange={e => update('description', e.target.value)} rows={2} placeholder="What this style does..." />
                  </div>
                  <div className="form-row">
                    <div>
                      <label>Target duration (s)</label>
                      <input className="mono" type="number" value={form.target_duration} onChange={e => update('target_duration', parseInt(e.target.value) || 60)} />
                    </div>
                    <div>
                      <label>Max clips</label>
                      <input className="mono" type="number" value={form.max_clips} onChange={e => update('max_clips', parseInt(e.target.value) || 20)} />
                    </div>
                  </div>
                </>
              )}

              {tab === 'voice' && (
                <>
                  <div className="form-group">
                    <label>Content guidelines</label>
                    <textarea value={form.content_guidelines} onChange={e => update('content_guidelines', e.target.value)} rows={3} placeholder="What content types to look for..." />
                  </div>
                  <div className="form-row">
                    <div>
                      <label>Keep (positive signals)</label>
                      <textarea value={form.keep_rules} onChange={e => update('keep_rules', e.target.value)} rows={5} placeholder="Patterns to retain..." />
                    </div>
                    <div>
                      <label>Remove (negative signals)</label>
                      <textarea value={form.remove_rules} onChange={e => update('remove_rules', e.target.value)} rows={5} placeholder="Patterns to discard..." />
                    </div>
                  </div>
                </>
              )}

              {tab === 'position' && (
                <>
                  <div className="form-group">
                    <label>Editorial positioning</label>
                    <textarea value={form.style_positioning} onChange={e => update('style_positioning', e.target.value)} rows={3} placeholder="Steady, pragmatic, sharp-tongued entrepreneur..." />
                  </div>
                  <div className="form-row">
                    <div>
                      <label>Min score (0-1)</label>
                      <input className="mono" type="number" step="0.05" min="0" max="1" value={form.rules.min_score} onChange={e => updateRule('min_score', parseFloat(e.target.value) || 0.7)} />
                    </div>
                    <div>
                      <label>Priority keywords</label>
                      <input className="mono" type="text" value={form.rules.priority_keywords?.join(', ') || ''} onChange={e => updateRule('priority_keywords', e.target.value.split(',').map(s => s.trim()).filter(Boolean))} placeholder="I think, the key point" />
                    </div>
                  </div>
                </>
              )}

              {tab === 'subtitle' && (
                <>
                  <div className="form-row">
                    <div>
                      <label>Font size (px)</label>
                      <input className="mono" type="number" value={form.subtitle_config?.font_size || 22} onChange={e => updateSub('font_size', parseInt(e.target.value) || 22)} />
                    </div>
                    <div>
                      <label>Vertical position (%)</label>
                      <input className="mono" type="number" min="0" max="100" value={Math.round((form.subtitle_config?.position || 0.33) * 100)} onChange={e => updateSub('position', (parseInt(e.target.value) || 33) / 100)} />
                    </div>
                    <div>
                      <label>Text color</label>
                      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                        <input type="color" value={form.subtitle_config?.txt_color || '#ffffff'} onChange={e => updateSub('txt_color', e.target.value)} />
                        <input type="text" value={form.subtitle_config?.txt_color || '#ffffff'} onChange={e => updateSub('txt_color', e.target.value)} />
                      </div>
                    </div>
                    <div>
                      <label>Stroke color</label>
                      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                        <input type="color" value={form.subtitle_config?.stroke_color || '#ffffff'} onChange={e => updateSub('stroke_color', e.target.value)} />
                        <input type="text" value={form.subtitle_config?.stroke_color || '#ffffff'} onChange={e => updateSub('stroke_color', e.target.value)} />
                      </div>
                    </div>
                    <div>
                      <label>Stroke width</label>
                      <input className="mono" type="number" step="0.5" min="0" max="5" value={form.subtitle_config?.stroke_width || 1} onChange={e => updateSub('stroke_width', parseFloat(e.target.value) || 1)} />
                    </div>
                    <div>
                      <label>Font</label>
                      <select value={form.subtitle_config?.font || 'Arial'} onChange={e => updateSub('font', e.target.value)}>
                        <option value="Arial">Arial</option>
                        <option value="PingFang SC">PingFang SC</option>
                        <option value="Noto Sans SC">Noto Sans SC</option>
                        <option value="Microsoft YaHei">Microsoft YaHei</option>
                        <option value="SimHei">SimHei</option>
                      </select>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-4)' }}>
                    {[
                      { label: 'Default', config: { font_size: 22, txt_color: 'white', stroke_color: 'white', stroke_width: 1, font: 'Arial', position: 0.33 } },
                      { label: 'Variety', config: { font_size: 24, txt_color: 'yellow', stroke_color: 'black', stroke_width: 2, font: 'Arial', position: 0.35 } },
                      { label: 'Documentary', config: { font_size: 20, txt_color: 'white', stroke_color: 'black', stroke_width: 1.5, font: 'PingFang SC', position: 0.30 } },
                    ].map(p => (
                      <button key={p.label} className="btn btn-sm" onClick={() => setForm(prev => ({ ...prev, subtitle_config: p.config }))}>
                        {p.label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setShowModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={save} disabled={!form.name}>
                {editing ? 'Save changes' : 'Create style'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default StyleManager