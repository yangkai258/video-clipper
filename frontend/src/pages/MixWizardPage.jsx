import { useState, useEffect } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'
import Icon from '../Icon'

// ponytail: 新建混剪向导 (v2.2.5)
// 3 步:
//   Step 1: 脚本输入 (textarea + AI 帮写 + 风险词实时检测高亮)
//   Step 2: 素材选择 (从 /mix/clips/library 拉候选 clips, 多选 tabs by project)
//   Step 3: 目标时长 + 确认 + 提交
// 提交: POST /api/v1/mix → 拿到 project_id 跳 /mix/:id

const API_BASE = '/api/v1'

const TARGET_DURATIONS = [
  { value: 30, label: '30s', desc: '抖音/快手 短视频' },
  { value: 60, label: '60s', desc: '抖音中视频' },
  { value: 180, label: '3分钟', desc: '视频号中长视频' },
  { value: 300, label: '5分钟', desc: '长视频引流款' },
]

export default function MixWizardPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [scriptText, setScriptText] = useState('')
  const [scriptSegments, setScriptSegments] = useState(null)  // LLM 解析后的 segments
  const [parsing, setParsing] = useState(false)
  const [riskResult, setRiskResult] = useState(null)
  const [candidates, setCandidates] = useState([])
  const [selectedClipIds, setSelectedClipIds] = useState([])
  const [libraryProject, setLibraryProject] = useState('all')
  const [targetDuration, setTargetDuration] = useState(60)
  const [submitting, setSubmitting] = useState(false)
  // v2.2.5: AI 帮写脚本 (Step 1)
  const [generating, setGenerating] = useState(false)
  const [aiTopic, setAiTopic] = useState('')

  // 实时风险词检测 (debounced)
  useEffect(() => {
    if (!scriptText.trim()) {
      setRiskResult(null)
      return
    }
    const t = setTimeout(async () => {
      try {
        const r = await axios.post(`${API_BASE}/mix/script-risk-check`, { script_text: scriptText })
        setRiskResult(r.data)
      } catch (e) {
        console.error('risk-check failed:', e)
      }
    }, 600)
    return () => clearTimeout(t)
  }, [scriptText])

  // 加载素材库
  useEffect(() => {
    if (step === 2) {
      loadLibrary()
    }
  }, [step])

  // v2.2.5: 进入页面也预加载素材库, 让 Step 1 的 AI 帮写有 clips_context 可传
  useEffect(() => {
    loadLibrary()
  }, [])

  const loadLibrary = async () => {
    try {
      const r = await axios.get(`${API_BASE}/mix/clips/library`)
      setCandidates(r.data.clips || [])
    } catch (e) {
      console.error('load library failed:', e)
    }
  }

  // v2.2.5: AI 帮写带货脚本 (Step 1 ✨ 按钮)
  const aiHelpWrite = async () => {
    setGenerating(true)
    try {
      const clips_context = (candidates || []).map(c => ({
        title: c.title || '',
        source_project_name: c.source_project_name || '',
        subtitle_text: c.subtitle_text_preview || '',
      }))
      const r = await axios.post(`${API_BASE}/mix/ai-help-write`, {
        topic: aiTopic,
        clips_context,
        target_duration_seconds: targetDuration,
      })
      if (r.data && r.data.script_text) {
        setScriptText(r.data.script_text)
      } else {
        alert('AI 帮写返回为空, 请重试')
      }
    } catch (e) {
      const msg = e.response?.data?.detail || e.message
      alert('AI 帮写失败：' + msg)
    } finally {
      setGenerating(false)
    }
  }

  // Step 1 → Step 2: 解析脚本 (LLM) — 必须有 segments 才能选素材
  const parseAndNext = async () => {
    if (!scriptText.trim()) {
      alert('请输入脚本内容')
      return
    }
    setParsing(true)
    try {
      // 通过 POST /mix 触发完整 pipeline (后端会先 parse 再 match)
      // 这里我们只是预览, 真正的 parse 留给后端
      // 但我们要拿到 segments 给用户预览
      // v2.2.4 简化: 不单独 preview, 直接到 step 2 让用户选素材
      setScriptSegments([{ position: 0, text: scriptText, keywords: [] }])  // 占位
      setStep(2)
    } catch (e) {
      alert('解析失败：' + e.message)
    } finally {
      setParsing(false)
    }
  }

  const toggleClip = (clipId) => {
    setSelectedClipIds(prev =>
      prev.includes(clipId) ? prev.filter(id => id !== clipId) : [...prev, clipId]
    )
  }

  // Step 3 → submit
  const submit = async () => {
    if (!scriptText.trim()) {
      alert('脚本不能为空')
      return
    }
    if (selectedClipIds.length === 0) {
      alert('至少选一个素材片段')
      return
    }
    setSubmitting(true)
    try {
      const r = await axios.post(`${API_BASE}/mix`, {
        name: `混剪 ${new Date().toLocaleString('zh-CN', { hour12: false }).slice(0, 16)}`,
        script_text: scriptText,
        target_duration_seconds: targetDuration,
        candidate_clip_ids: selectedClipIds,
      })
      const projectId = r.data.project_id
      navigate(`/mix/${projectId}`)
    } catch (e) {
      alert('提交失败：' + (e.response?.data?.detail || e.message))
    } finally {
      setSubmitting(false)
    }
  }

  // 风险词高亮渲染: 把命中词替换为 <mark>
  const renderHighlightedScript = () => {
    if (!riskResult || !riskResult.has_risk || !scriptText) {
      return <span style={{ whiteSpace: 'pre-wrap' }}>{scriptText || <span style={{ color: 'var(--text-dim)' }}>在此粘贴或撰写你的直播带货脚本…</span>}</span>
    }
    // 收集所有 hit positions, 排序去重叠
    const hits = []
    riskResult.hits.forEach(h => {
      h.positions.forEach(p => {
        hits.push({ start: p.start, end: p.end, category: h.category, word: h.word })
      })
    })
    hits.sort((a, b) => a.start - b.start)

    // 去重叠: 保留先出现的
    const cleaned = []
    let lastEnd = -1
    for (const h of hits) {
      if (h.start >= lastEnd) {
        cleaned.push(h)
        lastEnd = h.end
      }
    }

    const parts = []
    let cursor = 0
    cleaned.forEach((h, i) => {
      if (h.start > cursor) {
        parts.push(<span key={`t-${i}`}>{scriptText.slice(cursor, h.start)}</span>)
      }
      parts.push(
        <mark
          key={`h-${i}`}
          className={`risk-mark risk-${riskResult.level}`}
          title={`${h.category} · ${h.word}`}
        >
          {scriptText.slice(h.start, h.end)}
        </mark>
      )
      cursor = h.end
    })
    if (cursor < scriptText.length) {
      parts.push(<span key="tail">{scriptText.slice(cursor)}</span>)
    }
    return <span style={{ whiteSpace: 'pre-wrap' }}>{parts}</span>
  }

  return (
    <div className="wizard-page">
      {/* 步骤指示 */}
      <div className="wizard-steps">
        {[
          [1, '脚本'],
          [2, '素材'],
          [3, '时长与提交'],
        ].map(([n, label]) => (
          <div key={n} className={`wizard-step ${step === n ? 'active' : ''} ${step > n ? 'done' : ''}`}>
            <div className="wizard-step-num">{step > n ? <Icon name="check" size={12} /> : n}</div>
            <div className="wizard-step-label">{label}</div>
          </div>
        ))}
      </div>

      {/* Step 1: 脚本 */}
      {step === 1 && (
        <div className="wizard-pane">
          <div className="wizard-pane-header">
            <h2>输入直播带货脚本</h2>
            <p className="wizard-hint">支持纯文本，AI 会按关键词匹配片段并烧字幕</p>
          </div>

          <div className="wizard-script-grid">
            <div className="wizard-script-edit">
              {/* v2.2.5: AI 帮写 - 产品名/主题 + 按钮 */}
              <div className="ai-help-row">
                <input
                  type="text"
                  className="ai-topic-input"
                  placeholder="产品名/主题 (可选, 留空 AI 自动从素材库推断)"
                  value={aiTopic}
                  onChange={e => setAiTopic(e.target.value)}
                  disabled={generating}
                />
                <button
                  className="btn btn-ghost"
                  onClick={aiHelpWrite}
                  disabled={generating}
                  title="根据主题 + 素材库, AI 生成带货脚本"
                >
                  {generating ? (
                    <><Icon name="spinner" size={11} /> AI 撰写中...</>
                  ) : (
                    <>✨ AI 帮我写</>
                  )}
                </button>
              </div>
              <textarea
                className="script-textarea"
                placeholder="例如：这款防水固砂套装, 40+、50+朋友的福音。屋顶、外墙、阳台漏水都能用。"
                value={scriptText}
                onChange={e => setScriptText(e.target.value)}
                rows={10}
              />
              <div className="wizard-script-meta">
                <span>{scriptText.length} 字</span>
                {riskResult && riskResult.has_risk && (
                  <span className={`risk-badge risk-${riskResult.level}`}>
                    <Icon name="warning" size={11} />
                    {riskResult.total_risk_count} 个风险词 · {riskResult.level === 'high' ? '高' : riskResult.level === 'medium' ? '中' : '低'}
                  </span>
                )}
              </div>
            </div>

            <div className="wizard-script-preview">
              <div className="wizard-preview-label">实时预览（含风险词高亮）</div>
              <div className="wizard-preview-body">{renderHighlightedScript()}</div>
            </div>
          </div>

          {riskResult && riskResult.has_risk && (
            <div className={`risk-warn-box risk-${riskResult.level}`}>
              <div className="risk-warn-head">
                <Icon name="warning" size={14} />
                检测到 {riskResult.total_risk_count} 个抖音/广告法敏感词
              </div>
              <div className="risk-warn-hits">
                {riskResult.hits.slice(0, 6).map((h, i) => (
                  <span key={i} className={`risk-tag risk-${riskResult.level}`}>
                    {h.category} · {h.word} ×{h.count}
                  </span>
                ))}
                {riskResult.hits.length > 6 && (
                  <span className="risk-tag risk-dim">+{riskResult.hits.length - 6} 更多</span>
                )}
              </div>
              <div className="risk-warn-tip">
                提交时仍会确认。建议替换为合规表达（如下方建议），降低被平台拒审风险。
              </div>
            </div>
          )}

          <div className="wizard-footer">
            <button className="btn btn-ghost" onClick={() => navigate('/mix')}>
              <Icon name="chevronLeft" size={11} /> 返回
            </button>
            <button className="btn btn-primary" onClick={parseAndNext} disabled={!scriptText.trim() || parsing}>
              {parsing ? <><Icon name="spinner" size={11} /> 解析中...</> : <>下一步 · 选素材 <Icon name="chevronRight" size={11} /></>}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: 素材 */}
      {step === 2 && (
        <div className="wizard-pane">
          <div className="wizard-pane-header">
            <h2>选择素材片段</h2>
            <p className="wizard-hint">从已有的切片项目中勾选素材（{selectedClipIds.length} 已选）</p>
          </div>

          {/* 按项目分组 tabs */}
          <div className="tabs">
            <button
              className={`tab ${libraryProject === 'all' ? 'tab-active' : ''}`}
              onClick={() => setLibraryProject('all')}
            >
              全部 ({candidates.length})
            </button>
            {/* 按 source_project_name 分组 */}
            {Array.from(new Set(candidates.map(c => c.source_project_name).filter(Boolean))).map(pname => (
              <button
                key={pname}
                className={`tab ${libraryProject === pname ? 'tab-active' : ''}`}
                onClick={() => setLibraryProject(pname)}
              >
                {pname.slice(0, 18)} ({candidates.filter(c => c.source_project_name === pname).length})
              </button>
            ))}
          </div>

          <div className="library-grid">
            {candidates
              .filter(c => libraryProject === 'all' || c.source_project_name === libraryProject)
              .map(c => {
                const selected = selectedClipIds.includes(c.id)
                return (
                  <div
                    key={c.id}
                    className={`library-card ${selected ? 'selected' : ''}`}
                    onClick={() => toggleClip(c.id)}
                  >
                    {selected && <div className="library-card-check"><Icon name="check" size={14} /></div>}
                    <div className="library-card-title">{c.title || '(未命名片段)'}</div>
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
            <button className="btn btn-primary" onClick={() => setStep(3)} disabled={selectedClipIds.length === 0}>
              下一步 · 时长 <Icon name="chevronRight" size={11} />
            </button>
          </div>
        </div>
      )}

      {/* Step 3: 时长 + 提交 */}
      {step === 3 && (
        <div className="wizard-pane">
          <div className="wizard-pane-header">
            <h2>确认参数并提交</h2>
            <p className="wizard-hint">脚本片段会按关键词匹配素材并拼接，匹配率较低时会自动回退</p>
          </div>

          <div className="confirm-summary">
            <div className="confirm-row">
              <span className="confirm-label">脚本长度</span>
              <span className="confirm-value">{scriptText.length} 字</span>
            </div>
            <div className="confirm-row">
              <span className="confirm-label">已选素材</span>
              <span className="confirm-value">{selectedClipIds.length} 个片段</span>
            </div>
            {riskResult && riskResult.has_risk && (
              <div className={`confirm-row risk-${riskResult.level}`}>
                <span className="confirm-label">风险词</span>
                <span className="confirm-value">
                  {riskResult.total_risk_count} 个 · level={riskResult.level}
                  <span className="confirm-tip">提交后仍可人工确认</span>
                </span>
              </div>
            )}
          </div>

          <div className="confirm-section">
            <div className="confirm-section-label">目标时长</div>
            <div className="duration-options">
              {TARGET_DURATIONS.map(d => (
                <button
                  key={d.value}
                  className={`duration-card ${targetDuration === d.value ? 'selected' : ''}`}
                  onClick={() => setTargetDuration(d.value)}
                >
                  <div className="duration-card-value">{d.label}</div>
                  <div className="duration-card-desc">{d.desc}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="wizard-footer">
            <button className="btn btn-ghost" onClick={() => setStep(2)}>
              <Icon name="chevronLeft" size={11} /> 上一步
            </button>
            <button
              className="btn btn-primary"
              onClick={submit}
              disabled={submitting}
            >
              {submitting
                ? <><Icon name="spinner" size={11} /> 提交中...</>
                : <><Icon name="check" size={11} /> 提交生成</>}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


// 时间格式化工具 (跟 projectView 一致, 这里 inline 避免循环依赖)
function formatTC(sec) {
  if (!sec || sec < 0) return '—'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}