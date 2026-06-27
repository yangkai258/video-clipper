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
    font_size: 28,
    txt_color: 'white',
    stroke_color: 'black',
    stroke_width: 2,
    font: '/System/Library/Fonts/STHeiti Medium.ttc',
    position: 0.78
  }
}

function StyleManager({ navigate: navProp, location: locProp }) {
  const [styles, setStyles] = useState([])
  const [presets, setPresets] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(defaultStyle)
  const [tab, setTab] = useState('basic')
  const navigate = navProp || useNavigate()
  const location = locProp || useLocation()

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
      alert(`保存失败：${e.response?.data?.detail || e.message}`)
    }
  }

  const remove = async (id, name) => {
    if (!confirm(`确定删除「${name}」？`)) return
    try {
      await axios.delete(`${API_BASE}/styles/${id}`)
      loadStyles()
    } catch (e) { alert(`删除失败：${e.message}`) }
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
      <div className="topbar">
        <div className="topbar-right">
          <button className="btn btn-primary" onClick={openCreate}>+ 新建风格</button>
        </div>
      </div>

      <div className="content fade-in">
        <div className="content-header">
          <div>
            <div className="content-title">自定义风格</div>
            <div className="content-subtitle">{styles.length} 个 · AI 切片的编辑风格</div>
          </div>
        </div>

          {presets.length > 0 && (
            <>
              <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', fontFamily: 'var(--text-mono)', marginBottom: 'var(--space-3)' }}>
                从预设快速开始
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
                      <span>时长 <b style={{ color: 'var(--text-default)' }}>{p.target_duration}s</b></span>
                      <span>最多 <b style={{ color: 'var(--text-default)' }}>{p.max_clips}</b></span>
                    </div>
                    <div className="style-item-actions">
                      <button className="btn btn-ghost btn-sm" onClick={() => { applyPreset(p); openCreate(); }}>使用</button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', fontFamily: 'var(--text-mono)', marginBottom: 'var(--space-3)' }}>
            我的风格 / {styles.length}
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
                    <span>时长 <b style={{ color: 'var(--text-default)' }}>{s.target_duration}s</b></span>
                    <span>最多 <b style={{ color: 'var(--text-default)' }}>{s.max_clips}</b></span>
                  </div>
                  <div className="style-item-actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => openEdit(s)}>编辑</button>
                    <button className="btn btn-ghost btn-sm btn-danger" onClick={() => remove(s.id, s.name)}>✕</button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty">
              <div className="empty-icon">∅</div>
              <div className="empty-title">还没有自定义风格</div>
              <div className="empty-hint">创建一个，或从上方选个预设</div>
            </div>
          )}
      </div>

      {showModal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <div className="modal-title">
                <div className="modal-title-icon" />
                {editing ? `编辑 · ${editing.name}` : '新建风格'}
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowModal(false)}>✕</button>
            </div>

            <div className="tabs" style={{ paddingLeft: 'var(--space-6)' }}>
              {[['basic', '基础设置'], ['voice', '识别规则'], ['position', '风格定位'], ['subtitle', '字幕配置']].map(([k, label]) => (
                <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>
              ))}
            </div>

            <div className="modal-body">
              {tab === 'basic' && (
                <>
                  <div className="form-group">
                    <label>风格名称 *</label>
                    <input type="text" value={form.name} onChange={e => update('name', e.target.value)} placeholder="如：邹总直播切片" />
                  </div>
                  <div className="form-group">
                    <label>描述</label>
                    <textarea value={form.description} onChange={e => update('description', e.target.value)} rows={2} placeholder="这个风格做什么..." />
                  </div>
                  <div className="form-row">
                    <div>
                      <label>目标时长（秒/切片）</label>
                      <input className="mono" type="number" value={form.target_duration} onChange={e => update('target_duration', parseInt(e.target.value) || 60)} />
                    </div>
                    <div>
                      <label>最大切片数</label>
                      <input className="mono" type="number" value={form.max_clips} onChange={e => update('max_clips', parseInt(e.target.value) || 20)} />
                    </div>
                  </div>
                </>
              )}

              {tab === 'voice' && (
                <>
                  <div className="form-group">
                    <label>内容识别规则</label>
                    <textarea value={form.content_guidelines} onChange={e => update('content_guidelines', e.target.value)} rows={3} placeholder="要识别哪些内容类型，如经济时事/创业故事..." />
                  </div>
                  <div className="form-row">
                    <div>
                      <label>保留规则（正面信号）</label>
                      <textarea value={form.keep_rules} onChange={e => update('keep_rules', e.target.value)} rows={5} placeholder="要保留的模式..." />
                    </div>
                    <div>
                      <label>删除规则（负面信号）</label>
                      <textarea value={form.remove_rules} onChange={e => update('remove_rules', e.target.value)} rows={5} placeholder="要丢弃的模式..." />
                    </div>
                  </div>
                </>
              )}

              {tab === 'position' && (
                <>
                  <div className="form-group">
                    <label>风格定位</label>
                    <textarea value={form.style_positioning} onChange={e => update('style_positioning', e.target.value)} rows={3} placeholder="沉稳、务实、有阅历、敢说真话的企业家..." />
                  </div>
                  <div className="form-row">
                    <div>
                      <label>最低评分（0-1）</label>
                      <input className="mono" type="number" step="0.05" min="0" max="1" value={form.rules.min_score} onChange={e => updateRule('min_score', parseFloat(e.target.value) || 0.7)} />
                    </div>
                    <div>
                      <label>优先关键词（逗号分隔）</label>
                      <input className="mono" type="text" value={form.rules.priority_keywords?.join(', ') || ''} onChange={e => updateRule('priority_keywords', e.target.value.split(',').map(s => s.trim()).filter(Boolean))} placeholder="我觉得, 关键是, 最重要" />
                    </div>
                  </div>
                </>
              )}

              {tab === 'subtitle' && (
                <>
                  <div className="form-row">
                    <div>
                      <label>字体大小（像素）</label>
                      <input className="mono" type="number" value={form.subtitle_config?.font_size || 28} onChange={e => updateSub('font_size', parseInt(e.target.value) || 28)} />
                    </div>
                    <div>
                      <label>文字颜色</label>
                      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                        <input type="color" value={form.subtitle_config?.txt_color || '#ffffff'} onChange={e => updateSub('txt_color', e.target.value)} />
                        <input type="text" value={form.subtitle_config?.txt_color || '#ffffff'} onChange={e => updateSub('txt_color', e.target.value)} />
                      </div>
                    </div>
                    <div>
                      <label>描边颜色</label>
                      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                        <input type="color" value={form.subtitle_config?.stroke_color || '#000000'} onChange={e => updateSub('stroke_color', e.target.value)} />
                        <input type="text" value={form.subtitle_config?.stroke_color || '#000000'} onChange={e => updateSub('stroke_color', e.target.value)} />
                      </div>
                    </div>
                    <div>
                      <label>描边宽度</label>
                      <input className="mono" type="number" step="0.5" min="0" max="5" value={form.subtitle_config?.stroke_width || 2} onChange={e => updateSub('stroke_width', parseFloat(e.target.value) || 2)} />
                    </div>
                    <div>
                      <label>字体</label>
                      <select value={form.subtitle_config?.font || '/System/Library/Fonts/STHeiti Medium.ttc'} onChange={e => updateSub('font', e.target.value)}>
                        <option value="/System/Library/Fonts/STHeiti Medium.ttc">华文黑体（STHeiti，macOS 默认）</option>
                        <option value="/System/Library/Fonts/PingFang.ttc">苹方（PingFang）</option>
                        <option value="/System/Library/Fonts/Hiragino Sans GB.ttc">冬青黑体（Hiragino）</option>
                        <option value="/Library/Fonts/Songti.ttc">宋体（Songti）</option>
                        <option value="Arial">Arial（缺中文字符）</option>
                        <option value="PingFang SC">苹方 SC（系统名）</option>
                        <option value="Noto Sans SC">思源黑体（Noto Sans SC）</option>
                        <option value="Microsoft YaHei">微软雅黑（Windows）</option>
                        <option value="SimHei">黑体（SimHei）</option>
                      </select>
                    </div>
                  </div>

                  {/* === 字幕位置：滑块 + 快捷 + 9:16 预览 === */}
                  <div style={{ marginTop: 'var(--space-4)' }}>
                    <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
                      <span>字幕位置（视频高度）</span>
                      <span className="mono" style={{ color: 'var(--accent)', fontWeight: 600 }}>
                        {Math.round((form.subtitle_config?.position || 0.78) * 100)}%
                      </span>
                    </label>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 'var(--space-5)', alignItems: 'stretch' }}>
                      {/* 左侧：滑块 + 快捷按钮 */}
                      <div>
                        <input
                          type="range"
                          min="5" max="95" step="1"
                          value={Math.round((form.subtitle_config?.position || 0.78) * 100)}
                          onChange={e => updateSub('position', parseInt(e.target.value) / 100)}
                          style={{
                            width: '100%', accentColor: 'var(--accent)',
                            background: 'var(--bg-base)', height: '4px', borderRadius: '2px',
                            cursor: 'pointer'
                          }}
                        />
                        <div style={{
                          display: 'flex', justifyContent: 'space-between',
                          fontFamily: 'var(--text-mono)', fontSize: 10,
                          color: 'var(--text-dim)', marginTop: 'var(--space-1)'
                        }}>
                          <span>0% 顶部</span>
                          <span>50% 居中</span>
                          <span>100% 底部</span>
                        </div>
                        <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
                          {[
                            { label: '顶部', pos: 0.10, hint: '封面感，适合标题' },
                            { label: '居中', pos: 0.50, hint: '对白场景' },
                            { label: '底部', pos: 0.85, hint: '口播字幕位' },
                          ].map(p => (
                            <button
                              key={p.label}
                              type="button"
                              className={`btn btn-sm ${Math.abs((form.subtitle_config?.position || 0.78) - p.pos) < 0.03 ? 'btn-primary' : 'btn-ghost'}`}
                              onClick={() => updateSub('position', p.pos)}
                              title={p.hint}
                              style={{ flex: 1 }}
                            >
                              {p.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* 右侧：9:16 预览框 */}
                      <div style={{
                        position: 'relative',
                        width: '90px', height: '160px',
                        background: 'var(--bg-base)',
                        border: '1px solid var(--border-default)',
                        borderRadius: 'var(--radius-md)',
                        overflow: 'hidden',
                        flexShrink: 0
                      }}>
                        {/* 9:16 grid 标线 */}
                        <div style={{
                          position: 'absolute', left: 0, right: 0,
                          top: '33%', height: '1px', background: 'var(--border-subtle)'
                        }} />
                        <div style={{
                          position: 'absolute', left: 0, right: 0,
                          top: '66%', height: '1px', background: 'var(--border-subtle)'
                        }} />
                        {/* 字幕占位 */}
                        <div style={{
                          position: 'absolute', left: 0, right: 0,
                          top: `${(form.subtitle_config?.position || 0.78) * 100}%`,
                          transform: 'translateY(-50%)',
                          textAlign: 'center', padding: '0 4px',
                          color: form.subtitle_config?.txt_color || '#fff',
                          textShadow: `0 0 ${form.subtitle_config?.stroke_width || 2}px ${form.subtitle_config?.stroke_color || '#000'}`,
                          fontSize: 8,
                          fontFamily: 'var(--text-sans)',
                          fontWeight: 600,
                          whiteSpace: 'nowrap',
                          pointerEvents: 'none'
                        }}>
                          示例字幕
                        </div>
                        <div style={{
                          position: 'absolute', bottom: 2, left: 0, right: 0,
                          textAlign: 'center',
                          fontFamily: 'var(--text-mono)', fontSize: 8,
                          color: 'var(--text-dim)'
                        }}>
                          9:16
                        </div>
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-4)' }}>
                    {[
                      { label: '默认', config: { font_size: 28, txt_color: 'white', stroke_color: 'black', stroke_width: 2, font: '/System/Library/Fonts/STHeiti Medium.ttc', position: 0.78 } },
                      { label: '综艺风', config: { font_size: 32, txt_color: 'yellow', stroke_color: 'black', stroke_width: 2.5, font: '/System/Library/Fonts/STHeiti Medium.ttc', position: 0.78 } },
                      { label: '纪录片', config: { font_size: 24, txt_color: 'white', stroke_color: 'black', stroke_width: 2, font: '/System/Library/Fonts/PingFang.ttc', position: 0.82 } },
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
              <button className="btn btn-ghost" onClick={() => setShowModal(false)}>取消</button>
              <button className="btn btn-primary" onClick={save} disabled={!form.name}>
                {editing ? '保存修改' : '创建风格'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default StyleManager