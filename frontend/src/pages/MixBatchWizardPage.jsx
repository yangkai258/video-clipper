import { useState, useEffect } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'
import Icon from '../Icon'

// ponytail: 批量混剪 wizard (v2.2.6)
// 3 步:
//   Step 1: 公共脚本 + 目标时长 (会被变体覆盖)
//   Step 2: 多组素材 (变体 1/2/3... 加号加多组, 减号删)
//   Step 3: max_concurrent (1-3) + 确认 + 提交
// 提交: POST /api/v1/mix/batch → 拿 batch_id 跳详情页

const API_BASE = '/api/v1'

const TARGET_DURATIONS = [
  { value: 30, label: '30s' },
  { value: 60, label: '60s' },
  { value: 180, label: '3分钟' },
  { value: 300, label: '5分钟' },
]

export default function MixBatchWizardPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [name, setName] = useState('')
  const [commonScript, setCommonScript] = useState('')
  const [commonDuration, setCommonDuration] = useState(60)
  const [maxConcurrent, setMaxConcurrent] = useState(1)
  const [variations, setVariations] = useState([
    { name: '变体 1', script_text: '', candidate_clip_ids: [] },
  ])
  const [candidates, setCandidates] = useState([])
  const [activeSource, setActiveSource] = useState('all')
  const [activeProject, setActiveProject] = useState('all')
  const [activeVariationIdx, setActiveVariationIdx] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [riskResult, setRiskResult] = useState(null)

  // 加载素材库
  useEffect(() => {
    loadLibrary('all')
  }, [])

  const loadLibrary = async (source) => {
    try {
      const r = await axios.get(`${API_BASE}/mix/clips/library`, { params: { source } })
      setCandidates(r.data.clips || [])
    } catch (e) {
      console.error('load library failed:', e)
    }
  }

  // 实时风险词 (debounced)
  useEffect(() => {
    if (!commonScript.trim()) { setRiskResult(null); return }
    const t = setTimeout(async () => {
      try {
        const r = await axios.post(`${API_BASE}/mix/script-risk-check`, { script_text: commonScript })
        setRiskResult(r.data)
      } catch (e) {}
    }, 600)
    return () => clearTimeout(t)
  }, [commonScript])

  // 切 source tab 重新加载
  useEffect(() => {
    loadLibrary(activeSource)
  }, [activeSource])

  const addVariation = () => {
    setVariations(v => [...v, { name: `变体 ${v.length + 1}`, script_text: '', candidate_clip_ids: [] }])
  }
  const removeVariation = (idx) => {
    setVariations(v => v.filter((_, i) => i !== idx))
    if (activeVariationIdx >= variations.length - 1) {
      setActiveVariationIdx(Math.max(0, variations.length - 2))
    }
  }
  const updateVariation = (idx, field, value) => {
    setVariations(v => v.map((item, i) => i === idx ? { ...item, [field]: value } : item))
  }
  const toggleClipForVariation = (clipId) => {
    setVariations(v => v.map((item, i) => {
      if (i !== activeVariationIdx) return item
      const ids = item.candidate_clip_ids || []
      return { ...item, candidate_clip_ids: ids.includes(clipId) ? ids.filter(x => x !== clipId) : [...ids, clipId] }
    }))
  }

  const submit = async () => {
    if (!commonScript.trim()) { alert('请输入公共脚本'); return }
    if (variations.length === 0) { alert('至少一个变体'); return }
    if (variations.some(v => !v.candidate_clip_ids || v.candidate_clip_ids.length === 0)) {
      alert('每个变体至少选一个素材')
      return
    }
    setSubmitting(true)
    try {
      const payload_variations = variations.map(v => ({
        name: v.name,
        script_text: v.script_text || commonScript,
        target_duration_seconds: v.script_text ? commonDuration : commonDuration,
        candidate_clip_ids: v.candidate_clip_ids,
      }))
      const r = await axios.post(`${API_BASE}/mix/batch`, {
        name: name || `批量混剪 ${new Date().toLocaleString('zh-CN', { hour12: false }).slice(0, 16)}`,
        common_script_text: commonScript,
        common_target_duration: commonDuration,
        max_concurrent: maxConcurrent,
        variations: payload_variations,
      })
      navigate(`/mix/batch/${r.data.batch_id}`)
    } catch (e) {
      alert('提交失败: ' + (e.response?.data?.detail || e.message))
    } finally {
      setSubmitting(false)
    }
  }

  const filteredCandidates = candidates.filter(c => {
    if (activeSource !== 'all' && c.source_type !== activeSource) return false
    if (activeSource !== 'library' && activeProject !== 'all' && c.source_project_name !== activeProject) return false
    return true
  })

  return (
    <div className="wizard-page">
      <div className="wizard-steps">
        {[
          [1, '公共脚本'],
          [2, '多组素材'],
          [3, '并发与提交'],
        ].map(([n, label]) => (
          <div key={n} className={`wizard-step ${step === n ? 'active' : ''} ${step > n ? 'done' : ''}`}>
            <div className="wizard-step-num">{step > n ? <Icon name="check" size={12} /> : n}</div>
            <div className="wizard-step-label">{label}</div>
          </div>
        ))}
      </div>

      {/* Step 1: 公共脚本 */}
      {step === 1 && (
        <div className="wizard-pane">
          <div className="wizard-pane-header">
            <h2>公共配置</h2>
            <p className="wizard-hint">所有变体共享此脚本和目标时长，单个变体可在下一步覆盖</p>
          </div>

          <div style={{ marginBottom: 'var(--space-3)' }}>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-muted)', marginBottom: 4 }}>
              批次名（可选）
            </label>
            <input
              className="ai-topic-input"
              style={{ width: '100%' }}
              placeholder="如: 防水 A/B 测试"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>

          <div style={{ marginBottom: 'var(--space-3)' }}>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-muted)', marginBottom: 4 }}>
              公共脚本（所有变体默认用此脚本）
            </label>
            <textarea
              className="script-textarea"
              placeholder="例如: 防水材料, 持久耐用。屋顶、外墙、阳台都能用。"
              value={commonScript}
              onChange={e => setCommonScript(e.target.value)}
              rows={5}
            />
            {riskResult && riskResult.has_risk && (
              <div className={`risk-badge risk-${riskResult.level}`} style={{ marginTop: 6 }}>
                <Icon name="warning" size={11} />
                {riskResult.total_risk_count} 个风险词 · {riskResult.level}
              </div>
            )}
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-muted)', marginBottom: 8 }}>
              目标时长
            </label>
            <div className="duration-options">
              {TARGET_DURATIONS.map(d => (
                <button
                  key={d.value}
                  className={`duration-card ${commonDuration === d.value ? 'selected' : ''}`}
                  onClick={() => setCommonDuration(d.value)}
                >
                  <div className="duration-card-value">{d.label}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="wizard-footer">
            <button className="btn btn-ghost" onClick={() => navigate('/mix/batch')}>
              <Icon name="chevronLeft" size={11} /> 返回列表
            </button>
            <button className="btn btn-primary" onClick={() => setStep(2)} disabled={!commonScript.trim()}>
              下一步 · 多组素材 <Icon name="chevronRight" size={11} />
            </button>
          </div>
        </div>
      )}

      {/* Step 2: 多组素材 */}
      {step === 2 && (
        <div className="wizard-pane">
          <div className="wizard-pane-header">
            <h2>多组素材（{variations.length} 个变体）</h2>
            <p className="wizard-hint">每个变体独立选素材，可覆盖脚本</p>
          </div>

          {/* 变体 tabs */}
          <div className="tabs">
            {variations.map((v, i) => (
              <button
                key={i}
                className={`tab ${activeVariationIdx === i ? 'tab-active' : ''}`}
                onClick={() => setActiveVariationIdx(i)}
              >
                {v.name} ({v.candidate_clip_ids?.length || 0})
                {variations.length > 1 && (
                  <span
                    onClick={(e) => { e.stopPropagation(); removeVariation(i) }}
                    style={{ marginLeft: 6, color: '#ef4444', cursor: 'pointer' }}
                    title="删除此变体"
                  >
                    ×
                  </span>
                )}
              </button>
            ))}
            <button className="tab" onClick={addVariation}>
              <Icon name="plus" size={11} /> 添加变体
            </button>
          </div>

          {/* 当前变体的脚本覆盖 + 名称 */}
          <div style={{ marginBottom: 'var(--space-3)', padding: 'var(--space-3)', background: 'var(--bg-base)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
              <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', width: 80 }}>变体名</label>
              <input
                className="ai-topic-input"
                style={{ flex: 1 }}
                value={variations[activeVariationIdx]?.name || ''}
                onChange={e => updateVariation(activeVariationIdx, 'name', e.target.value)}
              />
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', width: 80, marginTop: 6 }}>
                覆盖脚本
              </label>
              <textarea
                className="script-textarea"
                style={{ flex: 1, minHeight: 60 }}
                placeholder={`留空使用公共脚本: "${commonScript.slice(0, 50)}${commonScript.length > 50 ? '...' : ''}"`}
                value={variations[activeVariationIdx]?.script_text || ''}
                onChange={e => updateVariation(activeVariationIdx, 'script_text', e.target.value)}
                rows={2}
              />
            </div>
          </div>

          {/* source tabs (切片/资源库) */}
          <div className="tabs">
            <button className={`tab ${activeSource === 'all' ? 'tab-active' : ''}`} onClick={() => setActiveSource('all')}>
              全部 ({candidates.filter(c => c.source_type !== 'library').length}+{candidates.filter(c => c.source_type === 'library').length})
            </button>
            <button className={`tab ${activeSource === 'project' ? 'tab-active' : ''}`} onClick={() => setActiveSource('project')}>
              切片库
            </button>
            <button className={`tab ${activeSource === 'library' ? 'tab-active' : ''}`} onClick={() => setActiveSource('library')}>
              资源库
            </button>
          </div>

          {/* 项目 tab (仅切片库) */}
          {activeSource !== 'library' && (
            <div className="tabs">
              <button className={`tab ${activeProject === 'all' ? 'tab-active' : ''}`} onClick={() => setActiveProject('all')}>
                全部
              </button>
              {Array.from(new Set(candidates.filter(c => activeSource === 'all' || c.source_type === activeSource).map(c => c.source_project_name).filter(Boolean))).slice(0, 10).map(pname => (
                <button
                  key={pname}
                  className={`tab ${activeProject === pname ? 'tab-active' : ''}`}
                  onClick={() => setActiveProject(pname)}
                >
                  {pname.slice(0, 14)}
                </button>
              ))}
            </div>
          )}

          <div className="library-grid">
            {filteredCandidates.map(c => {
              const selectedIds = variations[activeVariationIdx]?.candidate_clip_ids || []
              const selected = selectedIds.includes(c.id)
              return (
                <div
                  key={c.id}
                  className={`library-card ${selected ? 'selected' : ''}`}
                  onClick={() => toggleClipForVariation(c.id)}
                >
                  {selected && <div className="library-card-check"><Icon name="check" size={14} /></div>}
                  {c.source_type === 'library' && (
                    <div className="library-card-thumb">
                      <img
                        src={`/api/v1/library/thumbnails/${c.id}`}
                        alt={c.title}
                        loading="lazy"
                        onError={(e) => { e.currentTarget.style.display = 'none' }}
                      />
                      <span className="library-source-tag">资源库</span>
                    </div>
                  )}
                  <div className="library-card-title">{c.title || '(未命名)'}</div>
                  <div className="library-card-sub">
                    <span>{c.source_project_name}</span>
                    {c.duration && <span>· {formatTC(c.duration)}</span>}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="wizard-footer">
            <button className="btn btn-ghost" onClick={() => setStep(1)}>
              <Icon name="chevronLeft" size={11} /> 上一步
            </button>
            <button
              className="btn btn-primary"
              onClick={() => setStep(3)}
              disabled={variations.every(v => !v.candidate_clip_ids || v.candidate_clip_ids.length === 0)}
            >
              下一步 · 并发 <Icon name="chevronRight" size={11} />
            </button>
          </div>
        </div>
      )}

      {/* Step 3: max_concurrent + 确认 */}
      {step === 3 && (
        <div className="wizard-pane">
          <div className="wizard-pane-header">
            <h2>并发数与确认</h2>
            <p className="wizard-hint">考虑服务器性能: max_concurrent 越大越快但越耗资源</p>
          </div>

          <div className="confirm-summary">
            <div className="confirm-row">
              <span className="confirm-label">批次名</span>
              <span className="confirm-value">{name || '(自动命名)'}</span>
            </div>
            <div className="confirm-row">
              <span className="confirm-label">变体数</span>
              <span className="confirm-value">{variations.length}</span>
            </div>
            <div className="confirm-row">
              <span className="confirm-label">已选素材 (去重)</span>
              <span className="confirm-value">
                {[...new Set(variations.flatMap(v => v.candidate_clip_ids || []))].length} 个
              </span>
            </div>
            {riskResult && riskResult.has_risk && (
              <div className={`confirm-row risk-${riskResult.level}`}>
                <span className="confirm-label">风险词</span>
                <span className="confirm-value">
                  {riskResult.total_risk_count} 个 · level={riskResult.level}
                </span>
              </div>
            )}
          </div>

          <div className="confirm-section">
            <div className="confirm-section-label">并发数 (考虑服务器性能)</div>
            <div className="duration-options">
              {[
                { value: 1, label: '1', desc: '串行 (最稳, 零额外负载)' },
                { value: 2, label: '2', desc: '2 并行 (推荐, M2 8核)' },
                { value: 3, label: '3', desc: '3 并行 (M2 8核甜区上限)' },
              ].map(c => (
                <button
                  key={c.value}
                  className={`duration-card ${maxConcurrent === c.value ? 'selected' : ''}`}
                  onClick={() => setMaxConcurrent(c.value)}
                >
                  <div className="duration-card-value">{c.label}</div>
                  <div className="duration-card-desc">{c.desc}</div>
                </button>
              ))}
            </div>
            <div style={{ marginTop: 'var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
              实际耗时 ≈ (总任务数 ÷ 并发数) × 单任务耗时<br/>
              单任务通常 30-60s (LLM parse + ffmpeg + MoviePy 烧字幕)
            </div>
          </div>

          <div className="wizard-footer">
            <button className="btn btn-ghost" onClick={() => setStep(2)}>
              <Icon name="chevronLeft" size={11} /> 上一步
            </button>
            <button className="btn btn-primary" onClick={submit} disabled={submitting}>
              {submitting
                ? <><Icon name="spinner" size={11} /> 提交中...</>
                : <><Icon name="check" size={11} /> 提交 {variations.length} 个变体</>}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


// 时间格式化 (避免循环依赖)
function formatTC(sec) {
  if (!sec || sec < 0) return '—'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}