import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
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
  const [tab, setTab] = useState('basic') // basic | voice | style | subtitle
  const navigate = useNavigate()

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
    if (!confirm(`Delete style "${name}"?`)) return
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
    <>
      <div className="status-bar">
        <div className="status-bar-left">
          <span className="status-brand"><span className="dot"></span>VIDEO CLIPPER</span>
          <span className="status-divider"></span>
          <span>STYLE MANAGER</span>
        </div>
        <div className="status-bar-right">
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/')}>← BACK</button>
        </div>
      </div>

      <div className="container fade-in">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 'var(--space-5)' }}>
          <div>
            <h1>STYLES</h1>
            <div className="section-label" style={{ marginBottom: 0 }}>CUSTOM EDITORIAL VOICES</div>
          </div>
          <button className="btn btn-primary" onClick={openCreate}>
            + NEW STYLE
          </button>
        </div>

        {/* Presets quick-apply */}
        <div className="section-label">PRESETS · CLICK TO APPLY</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-2)', marginBottom: 'var(--space-6)' }}>
          {presets.map((p, i) => (
            <button
              key={p.id}
              className="strategy-track"
              onClick={() => { applyPreset(p); setShowModal(true); setEditing(null); setTab('voice') }}
            >
              <div className="strategy-track-id">{String(i + 1).padStart(2, '0')}</div>
              <div className="strategy-track-content">
                <div className="strategy-track-name">{p.name}</div>
                <div className="strategy-track-meta">
                  <span><span className="meta-key">DUR</span> <span className="meta-val">{p.target_duration}s</span></span>
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* Custom styles */}
        <div className="section-label">CUSTOM STYLES / {styles.length}</div>

        {styles.length > 0 ? (
          <div className="timeline-row">
            {styles.map((s, i) => (
              <div key={s.id} className="reel-card" data-status="completed">
                <div className="reel-status-dot"></div>
                <div className="reel-info">
                  <div className="reel-name">{s.name}</div>
                  <div className="reel-meta">
                    <span>{s.target_duration}s/CLIP</span>
                    <span className="reel-meta-divider"></span>
                    <span>MAX {s.max_clips}</span>
                    {s.style_positioning && (
                      <>
                        <span className="reel-meta-divider"></span>
                        <span className="rule-tag positioning">🎯 {s.style_positioning.substring(0, 30)}{s.style_positioning.length > 30 ? '...' : ''}</span>
                      </>
                    )}
                  </div>
                  {s.content_guidelines && (
                    <div className="field-block" style={{ marginTop: 'var(--space-2)' }}>
                      <div className="field-block-label">CONTENT GUIDE</div>
                      <div className="field-block-content">{s.content_guidelines.substring(0, 80)}{s.content_guidelines.length > 80 ? '...' : ''}</div>
                    </div>
                  )}
                </div>
                <div className="reel-actions">
                  <button className="btn btn-ghost btn-sm" onClick={() => openEdit(s)}>EDIT</button>
                  <button className="btn btn-ghost btn-sm" style={{ color: 'var(--status-error)' }} onClick={() => remove(s.id, s.name)}>✕</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <div style={{ fontSize: 48, opacity: 0.2 }}>∅</div>
            <div className="empty-state-title">NO CUSTOM STYLES · CREATE ONE</div>
          </div>
        )}

        {/* Editor modal */}
        {showModal && (
          <div className="modal-overlay">
            <div className="modal-content">
              <div className="modal-header">
                <div className="modal-title">{editing ? `EDIT · ${editing.name}` : 'NEW STYLE'}</div>
                <button className="btn btn-ghost btn-sm" onClick={() => setShowModal(false)}>✕</button>
              </div>

              {/* Tabs */}
              <div className="tabs" style={{ paddingLeft: 'var(--space-5)' }}>
                {[
                  ['basic', '01 BASIC'],
                  ['voice', '02 VOICE'],
                  ['style', '03 POSITIONING'],
                  ['subtitle', '04 SUBTITLE'],
                ].map(([k, label]) => (
                  <button
                    key={k}
                    className={`tab ${tab === k ? 'active' : ''}`}
                    onClick={() => setTab(k)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className="modal-body">
                {/* Basic tab */}
                {tab === 'basic' && (
                  <>
                    <label>NAME *</label>
                    <input type="text" value={form.name} onChange={e => update('name', e.target.value)} placeholder="e.g. ZOU_LIVESTREAM" />
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
                      <div>
                        <label>TARGET DURATION (s)</label>
                        <input className="mono-input" type="number" value={form.target_duration} onChange={e => update('target_duration', parseInt(e.target.value) || 60)} />
                      </div>
                      <div>
                        <label>MAX CLIPS</label>
                        <input className="mono-input" type="number" value={form.max_clips} onChange={e => update('max_clips', parseInt(e.target.value) || 20)} />
                      </div>
                    </div>
                    <label style={{ marginTop: 'var(--space-3)' }}>DESCRIPTION</label>
                    <textarea value={form.description} onChange={e => update('description', e.target.value)} rows={2} placeholder="What this style does..." />
                  </>
                )}

                {/* Voice tab */}
                {tab === 'voice' && (
                  <>
                    <label>CONTENT GUIDELINES</label>
                    <textarea
                      value={form.content_guidelines}
                      onChange={e => update('content_guidelines', e.target.value)}
                      rows={4}
                      placeholder="1. Economic analysis&#10;2. Founder stories&#10;3. Hot takes"
                    />

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
                      <div>
                        <label>KEEP (positive signal)</label>
                        <textarea
                          value={form.keep_rules}
                          onChange={e => update('keep_rules', e.target.value)}
                          rows={6}
                          placeholder="1. Complete arguments&#10;2. Quotable moments"
                        />
                      </div>
                      <div>
                        <label>REMOVE (negative signal)</label>
                        <textarea
                          value={form.remove_rules}
                          onChange={e => update('remove_rules', e.target.value)}
                          rows={6}
                          placeholder="1. Long silences&#10;2. Repetition"
                        />
                      </div>
                    </div>
                  </>
                )}

                {/* Style tab */}
                {tab === 'style' && (
                  <>
                    <label>EDITORIAL POSITIONING</label>
                    <textarea
                      value={form.style_positioning}
                      onChange={e => update('style_positioning', e.target.value)}
                      rows={3}
                      placeholder="Steady, pragmatic, experienced entrepreneur with a sharp tongue"
                    />
                    <label style={{ marginTop: 'var(--space-3)' }}>MIN SCORE (0-1)</label>
                    <input
                      className="mono-input"
                      type="number" step="0.05" min="0" max="1"
                      value={form.rules.min_score}
                      onChange={e => updateRule('min_score', parseFloat(e.target.value) || 0.7)}
                    />
                    <label style={{ marginTop: 'var(--space-3)' }}>PRIORITY KEYWORDS (comma-separated)</label>
                    <input
                      className="mono-input"
                      type="text"
                      value={form.rules.priority_keywords?.join(', ') || ''}
                      onChange={e => updateRule('priority_keywords', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                      placeholder="I think, the key point is"
                    />
                  </>
                )}

                {/* Subtitle tab */}
                {tab === 'subtitle' && (
                  <>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
                      <div>
                        <label>FONT SIZE (px)</label>
                        <input className="mono-input" type="number" value={form.subtitle_config?.font_size || 22} onChange={e => updateSub('font_size', parseInt(e.target.value) || 22)} />
                      </div>
                      <div>
                        <label>VERTICAL POSITION (%)</label>
                        <input className="mono-input" type="number" min="0" max="100" value={Math.round((form.subtitle_config?.position || 0.33) * 100)} onChange={e => updateSub('position', (parseInt(e.target.value) || 33) / 100)} />
                      </div>
                      <div>
                        <label>TEXT COLOR</label>
                        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                          <input type="color" value={form.subtitle_config?.txt_color || '#ffffff'} onChange={e => updateSub('txt_color', e.target.value)} />
                          <input type="text" value={form.subtitle_config?.txt_color || '#ffffff'} onChange={e => updateSub('txt_color', e.target.value)} />
                        </div>
                      </div>
                      <div>
                        <label>STROKE COLOR</label>
                        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                          <input type="color" value={form.subtitle_config?.stroke_color || '#ffffff'} onChange={e => updateSub('stroke_color', e.target.value)} />
                          <input type="text" value={form.subtitle_config?.stroke_color || '#ffffff'} onChange={e => updateSub('stroke_color', e.target.value)} />
                        </div>
                      </div>
                      <div>
                        <label>STROKE WIDTH</label>
                        <input className="mono-input" type="number" step="0.5" min="0" max="5" value={form.subtitle_config?.stroke_width || 1} onChange={e => updateSub('stroke_width', parseFloat(e.target.value) || 1)} />
                      </div>
                      <div>
                        <label>FONT FAMILY</label>
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
                        { label: 'DEFAULT', config: { font_size: 22, txt_color: 'white', stroke_color: 'white', stroke_width: 1, font: 'Arial', position: 0.33 } },
                        { label: 'VARIETY', config: { font_size: 24, txt_color: 'yellow', stroke_color: 'black', stroke_width: 2, font: 'Arial', position: 0.35 } },
                        { label: 'DOC', config: { font_size: 20, txt_color: 'white', stroke_color: 'black', stroke_width: 1.5, font: 'PingFang SC', position: 0.30 } },
                      ].map(preset => (
                        <button
                          key={preset.label}
                          className="btn btn-sm"
                          onClick={() => setForm(prev => ({ ...prev, subtitle_config: preset.config }))}
                        >
                          {preset.label}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <div className="modal-footer">
                <button className="btn btn-ghost" onClick={() => setShowModal(false)}>CANCEL</button>
                <button className="btn btn-primary" onClick={save} disabled={!form.name}>
                  {editing ? 'SAVE' : 'CREATE'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}

export default StyleManager