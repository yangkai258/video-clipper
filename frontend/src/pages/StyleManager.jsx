import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

const API_BASE = '/api/v1'

function StyleManager() {
  const [styles, setStyles] = useState([])
  const [presets, setPresets] = useState([])
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingStyle, setEditingStyle] = useState(null)
  const navigate = useNavigate()

  // 新建风格的默认值
  const defaultStyle = {
    name: '',
    description: '',
    target_duration: 60,
    max_clips: 20,
    content_types: [],
    rules: {
      min_score: 0.7,
      priority_keywords: []
    },
    content_guidelines: '',
    keep_rules: '',
    remove_rules: '',
    style_positioning: '',
    // 字幕配置默认值
    subtitle_config: {
      font_size: 22,
      txt_color: 'white',
      stroke_color: 'white',
      stroke_width: 1,
      font: 'Arial',
      position: 0.33
    }
  }

  const [formData, setFormData] = useState(defaultStyle)

  // 加载风格列表
  const loadStyles = async () => {
    try {
      const res = await axios.get(`${API_BASE}/styles`)
      setStyles(res.data)
    } catch (error) {
      console.error('加载风格列表失败:', error)
    }
  }

  // 加载预设策略
  const loadPresets = async () => {
    try {
      const res = await axios.get(`${API_BASE}/strategies/presets`)
      setPresets(res.data.strategies)
    } catch (error) {
      console.error('加载预设策略失败:', error)
    }
  }

  useEffect(() => {
    loadStyles()
    loadPresets()
  }, [])

  // 打开创建弹窗
  const handleCreate = () => {
    setEditingStyle(null)
    setFormData(defaultStyle)
    setShowCreateModal(true)
  }

  // 打开编辑弹窗
  const handleEdit = (style) => {
    setEditingStyle(style)
    setFormData({
      ...style,
      content_types: style.content_types || [],
      rules: style.rules || { min_score: 0.7, priority_keywords: [] },
      subtitle_config: style.subtitle_config || defaultStyle.subtitle_config
    })
    setShowCreateModal(true)
  }

  // 保存风格（创建或更新）
  const handleSave = async () => {
    try {
      if (editingStyle) {
        await axios.put(`${API_BASE}/styles/${editingStyle.id}`, formData)
        alert('✅ 风格已更新')
      } else {
        await axios.post(`${API_BASE}/styles`, formData)
        alert('✅ 风格已创建')
      }
      setShowCreateModal(false)
      loadStyles()
    } catch (error) {
      alert(`保存失败：${error.response?.data?.detail || error.message}`)
    }
  }

  // 删除风格
  const handleDelete = async (styleId, styleName) => {
    if (!confirm(`确定要删除风格 "${styleName}" 吗？此操作不可恢复。`)) return

    try {
      await axios.delete(`${API_BASE}/styles/${styleId}`)
      alert('风格已删除')
      loadStyles()
    } catch (error) {
      alert(`删除失败：${error.message}`)
    }
  }

  // 应用预设策略
  const applyPreset = (preset) => {
    setFormData({
      ...formData,
      name: preset.name.split(' ').slice(1).join(' '),
      description: preset.description,
      target_duration: preset.target_duration,
      max_clips: preset.max_clips,
      content_types: preset.content_types,
      rules: preset.rules,
      subtitle_config: defaultStyle.subtitle_config  // 预设风格使用默认字幕配置
    })
  }

  // 更新表单字段
  const updateField = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const updateRule = (key, value) => {
    setFormData(prev => ({
      ...prev,
      rules: { ...prev.rules, [key]: value }
    }))
  }

  return (
    <div className="container fade-in">
      {/* 页面头部 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1>✂️ 切片风格管理</h1>
        <button className="btn btn-primary" onClick={handleCreate}>
          ➕ 创建新风格
        </button>
      </div>

      {/* 预设策略快捷入口 */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <h2>📦 预设策略（快捷应用）</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginTop: '16px' }}>
          {presets.map(preset => (
            <button
              key={preset.id}
              className="btn btn-secondary"
              onClick={() => applyPreset(preset)}
              style={{ textAlign: 'left', padding: '12px' }}
            >
              <div style={{ fontSize: '20px', marginBottom: '4px' }}>{preset.name.split(' ')[0]}</div>
              <div style={{ fontSize: 'var(--text-sm)' }}>{preset.name.split(' ').slice(1).join(' ')}</div>
            </button>
          ))}
        </div>
      </div>

      {/* 风格列表 */}
      <h2>📋 我的风格 ({styles.length})</h2>
      
      {styles.length > 0 ? (
        <div className="project-grid">
          {styles.map(style => (
            <div key={style.id} className="card fade-in">
              <div className="project-card-header">
                <h3 className="project-title">{style.name}</h3>
              </div>
              
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginTop: '8px' }}>
                {style.description}
              </p>
              
              <div style={{ display: 'flex', gap: '12px', marginTop: '12px', fontSize: 'var(--text-sm)' }}>
                <span>⏱️ {style.target_duration}秒/切片</span>
                <span>📹 最多{style.max_clips}个</span>
              </div>

              {/* 内容识别规则 */}
              {style.content_guidelines && (
                <div className="field-block">
                  <div className="field-block-label">📌 内容识别</div>
                  <div className="field-block-content">{style.content_guidelines}</div>
                </div>
              )}

              {/* 保留/删除规则 */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
                {style.keep_rules && (
                  <div className="field-block">
                    <div className="field-block-label">✅ 保留</div>
                    <div className="field-block-content">{style.keep_rules}</div>
                  </div>
                )}
                {style.remove_rules && (
                  <div className="field-block">
                    <div className="field-block-label">❌ 删除</div>
                    <div className="field-block-content">{style.remove_rules}</div>
                  </div>
                )}
              </div>

              {/* 风格定位 */}
              {style.style_positioning && (
                <div style={{ marginTop: 'var(--space-3)' }}>
                  <span className="rule-tag positioning">🎯 {style.style_positioning}</span>
                </div>
              )}

              {/* 字幕配置 */}
              {style.subtitle_config && (
                <div className="field-block">
                  <div className="field-block-label">🎬 字幕配置</div>
                  <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginTop: 'var(--space-1)' }}>
                    <span className="rule-tag content">📏 {style.subtitle_config.font_size}px</span>
                    <span className="rule-tag content">🎨 {style.subtitle_config.txt_color}/{style.subtitle_config.stroke_color}</span>
                    <span className="rule-tag content">📍 {Math.round(style.subtitle_config.position * 100)}% 高度</span>
                  </div>
                </div>
              )}
              
              {/* 操作按钮 */}
              <div className="project-actions" style={{ marginTop: '16px' }}>
                <button className="btn btn-secondary btn-sm" onClick={() => handleEdit(style)}>
                  ✏️ 编辑
                </button>
                <button className="btn btn-danger btn-sm" onClick={() => handleDelete(style.id, style.name)}>
                  🗑️ 删除
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card" style={{ textAlign: 'center', padding: '48px' }}>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-lg)' }}>
            暂无自定义风格，创建一个吧！
          </p>
        </div>
      )}

      {/* 创建/编辑弹窗 */}
      {showCreateModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h2 style={{ marginBottom: '24px' }}>
              {editingStyle ? '✏️ 编辑风格' : '➕ 创建新风格'}
            </h2>

            {/* 基础设置 */}
            <div style={{ marginBottom: '24px' }}>
              <h3>基础设置</h3>
              <div style={{ display: 'grid', gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
                <div>
                  <label>风格名称 *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => updateField('name', e.target.value)}
                    placeholder="如：邹总直播切片"
                  />
                </div>
                <div>
                  <label>描述</label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => updateField('description', e.target.value)}
                    placeholder="风格描述..."
                    rows={2}
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
                  <div>
                    <label>目标时长（秒/切片）</label>
                    <input
                      type="number"
                      value={formData.target_duration}
                      onChange={(e) => updateField('target_duration', parseInt(e.target.value) || 60)}
                    />
                  </div>
                  <div>
                    <label>最大切片数</label>
                    <input
                      type="number"
                      value={formData.max_clips}
                      onChange={(e) => updateField('max_clips', parseInt(e.target.value) || 20)}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* 内容识别规则 */}
            <div style={{ marginBottom: '24px' }}>
              <h3>📌 内容识别规则</h3>
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                描述需要识别的内容类型，如"经济时事/创业故事/连麦互动"
              </p>
              <textarea
                value={formData.content_guidelines}
                onChange={(e) => updateField('content_guidelines', e.target.value)}
                placeholder="1. 经济实事/宏观解读&#10;2. 邹总亲身经历/创业故事&#10;3. 连麦互动 + 行业分析"
                rows={4}
                style={{ marginTop: 'var(--space-3)' }}
              />
            </div>

            {/* 保留/删除规则 */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', marginBottom: '24px' }}>
              <div>
                <h3>✅ 保留规则</h3>
                <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                  需要保留的内容类型
                </p>
                <textarea
                  value={formData.keep_rules}
                  onChange={(e) => updateField('keep_rules', e.target.value)}
                  placeholder="1. 保留完整逻辑&#10;2. 保留金句、总结&#10;3. 保留核心回答"
                  rows={6}
                  style={{ marginTop: 'var(--space-3)' }}
                />
              </div>
              <div>
                <h3>❌ 删除规则</h3>
                <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                  需要删除的内容类型
                </p>
                <textarea
                  value={formData.remove_rules}
                  onChange={(e) => updateField('remove_rules', e.target.value)}
                  placeholder="1. 删除长时间沉默&#10;2. 删除重复啰嗦&#10;3. 删除无关闲聊"
                  rows={6}
                  style={{ marginTop: 'var(--space-3)' }}
                />
              </div>
            </div>

            {/* 风格定位 */}
            <div style={{ marginBottom: '24px' }}>
              <h3>🎯 风格定位</h3>
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                描述人设和风格，如"沉稳、务实、有阅历的企业家"
              </p>
              <textarea
                value={formData.style_positioning}
                onChange={(e) => updateField('style_positioning', e.target.value)}
                placeholder="沉稳、务实、有阅历、懂商业、敢说真话的企业家"
                rows={2}
                style={{ marginTop: 'var(--space-3)' }}
              />
            </div>

            {/* 字幕配置 */}
            <div style={{ marginBottom: '24px' }}>
              <h3>🎬 字幕配置</h3>
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                配置字幕样式，适用于该风格的所有视频
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', marginTop: 'var(--space-3)' }}>
                {/* 字体大小 */}
                <div>
                  <label>字体大小 (px)</label>
                  <input
                    type="number"
                    value={formData.subtitle_config?.font_size || 22}
                    onChange={(e) => updateField('subtitle_config', { ...formData.subtitle_config, font_size: parseInt(e.target.value) || 22 })}
                  />
                </div>

                {/* 垂直位置 */}
                <div>
                  <label>垂直位置 (视频高度的 %)</label>
                  <input
                    type="number"
                    step="1"
                    min="0"
                    max="100"
                    value={Math.round((formData.subtitle_config?.position || 0.33) * 100)}
                    onChange={(e) => updateField('subtitle_config', { ...formData.subtitle_config, position: (parseInt(e.target.value) || 33) / 100 })}
                  />
                </div>

                {/* 文字颜色 */}
                <div>
                  <label>文字颜色</label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                    <input
                      type="color"
                      value={formData.subtitle_config?.txt_color || '#ffffff'}
                      onChange={(e) => updateField('subtitle_config', { ...formData.subtitle_config, txt_color: e.target.value })}
                    />
                    <input
                      type="text"
                      value={formData.subtitle_config?.txt_color || '#ffffff'}
                      onChange={(e) => updateField('subtitle_config', { ...formData.subtitle_config, txt_color: e.target.value })}
                    />
                  </div>
                </div>

                {/* 描边颜色 */}
                <div>
                  <label>描边颜色</label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                    <input
                      type="color"
                      value={formData.subtitle_config?.stroke_color || '#ffffff'}
                      onChange={(e) => updateField('subtitle_config', { ...formData.subtitle_config, stroke_color: e.target.value })}
                    />
                    <input
                      type="text"
                      value={formData.subtitle_config?.stroke_color || '#ffffff'}
                      onChange={(e) => updateField('subtitle_config', { ...formData.subtitle_config, stroke_color: e.target.value })}
                    />
                  </div>
                </div>

                {/* 描边宽度 */}
                <div>
                  <label>描边宽度</label>
                  <input
                    type="number"
                    step="0.5"
                    min="0"
                    max="5"
                    value={formData.subtitle_config?.stroke_width || 1}
                    onChange={(e) => updateField('subtitle_config', { ...formData.subtitle_config, stroke_width: parseFloat(e.target.value) || 1 })}
                  />
                </div>

                {/* 字体选择 */}
                <div>
                  <label>字体</label>
                  <select
                    value={formData.subtitle_config?.font || 'Arial'}
                    onChange={(e) => updateField('subtitle_config', { ...formData.subtitle_config, font: e.target.value })}
                  >
                    <option value="Arial">Arial (默认)</option>
                    <option value="PingFang SC">PingFang SC (苹果方)</option>
                    <option value="Noto Sans SC">Noto Sans SC (思源黑体)</option>
                    <option value="Microsoft YaHei">Microsoft YaHei (微软雅黑)</option>
                    <option value="SimHei">SimHei (黑体)</option>
                  </select>
                </div>
              </div>

              {/* 预设快捷按钮 */}
              <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => updateField('subtitle_config', {
                    font_size: 22,
                    txt_color: 'white',
                    stroke_color: 'white',
                    stroke_width: 1,
                    font: 'Arial',
                    position: 0.33
                  })}
                >
                  📋 默认（白字白边 33%）
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => updateField('subtitle_config', {
                    font_size: 24,
                    txt_color: 'yellow',
                    stroke_color: 'black',
                    stroke_width: 2,
                    font: 'Arial',
                    position: 0.35
                  })}
                >
                  🎬 综艺风（黄字黑边）
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => updateField('subtitle_config', {
                    font_size: 20,
                    txt_color: 'white',
                    stroke_color: 'black',
                    stroke_width: 1.5,
                    font: 'PingFang SC',
                    position: 0.30
                  })}
                >
                  📺 纪录片风（白字黑边）
                </button>
              </div>
            </div>

            {/* 高级规则 */}
            <div style={{ marginBottom: '24px' }}>
              <h3>⚙️ 高级规则</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
                <div>
                  <label>最低评分阈值 (0-1)</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={formData.rules.min_score}
                    onChange={(e) => updateRule('min_score', parseFloat(e.target.value) || 0.7)}
                  />
                </div>
                <div>
                  <label>优先关键词（逗号分隔）</label>
                  <input
                    type="text"
                    value={formData.rules.priority_keywords?.join(', ') || ''}
                    onChange={(e) => updateRule('priority_keywords', e.target.value.split(',').map(k => k.trim()).filter(k => k))}
                    placeholder="我觉得，我认为，关键是"
                  />
                </div>
              </div>
            </div>

            {/* 操作按钮 */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowCreateModal(false)}
              >
                取消
              </button>
              <button
                className="btn btn-primary"
                onClick={handleSave}
                disabled={!formData.name}
              >
                {editingStyle ? '保存修改' : '创建风格'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 返回主页按钮 */}
      <div style={{ marginTop: '24px', textAlign: 'center' }}>
        <button className="btn btn-secondary" onClick={() => navigate('/')}>
          ← 返回首页
        </button>
      </div>
    </div>
  )
}

export default StyleManager
