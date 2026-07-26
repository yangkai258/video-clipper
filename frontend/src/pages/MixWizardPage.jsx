import { useState, useEffect } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'
import Icon from '../Icon'  // eslint-disable-line no-unused-vars

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
  // v2.2.5: 素材库 source 切换 — 'all' (混合) / 'project' (切片项目) / 'library' (资源库)
  const [librarySource, setLibrarySource] = useState('all')
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

  // v2.2.35: 实时脚本分段预览 (debounced 1.5s, 走 /mix/parse-script)
  const [segmentPreview, setSegmentPreview] = useState(null)  // [{position, text, keywords}, ...]
  const [parsingSegments, setParsingSegments] = useState(false)
  const [segmentParseError, setSegmentParseError] = useState(null)
  useEffect(() => {
    if (!scriptText.trim() || scriptText.length < 20) {
      setSegmentPreview(null)
      setSegmentParseError(null)
      return
    }
    const t = setTimeout(async () => {
      setParsingSegments(true)
      setSegmentParseError(null)
      try {
        const r = await axios.post(`${API_BASE}/mix/parse-script`, {
          script_text: scriptText,
          target_duration_seconds: targetDuration,
        })
        setSegmentPreview(r.data.segments || [])
      } catch (e) {
        console.error('parse-script failed:', e)
        setSegmentParseError(e.response?.data?.detail || e.message)
        setSegmentPreview(null)
      } finally {
        setParsingSegments(false)
      }
    }, 1500)
    return () => clearTimeout(t)
  }, [scriptText, targetDuration])

  // 加载素材库
  useEffect(() => {
    if (step === 2) {
      loadLibrary()
    }
  }, [step, librarySource])  // eslint-disable-line react-hooks/exhaustive-deps

  // v2.2.5: 进入页面也预加载素材库 (默认 all), 让 Step 1 的 AI 帮写有 clips_context 可传
  useEffect(() => {
    loadLibrary('all')
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // v2.2.41: Step 2 按段预选 — 进入时调 /mix/preview-match 拿每段 top-N 候选
  const [previews, setPreviews] = useState(null)  // [{position, top_clips: [...]}]
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState(null)
  const [showSegments, setShowSegments] = useState(true)  // 默认展开按段预选
  useEffect(() => {
    // 仅在 Step 2 + 有 segments + 有 candidates 时才调
    if (step !== 2 || !scriptSegments || scriptSegments.length === 0) return
    if (candidates.length === 0) {
      setPreviews(null)
      return
    }
    setPreviewLoading(true)
    setPreviewError(null)
    const candidateIds = candidates.map(c => c.id)
    axios.post(`${API_BASE}/mix/preview-match`, {
      segments: scriptSegments,
      candidate_clip_ids: candidateIds,
      top_n: 3,
      target_duration_seconds: targetDuration,
    }).then(r => {
      setPreviews(r.data.previews || [])
      // v2.2.41: 自动预选 top-1 (user 可改)
      const preselected = new Set()
      ;(r.data.previews || []).forEach(p => {
        if (p.top_clips && p.top_clips.length > 0) {
          preselected.add(p.top_clips[0].clip_id)
        }
      })
      // 合并到现有 selectedClipIds (不覆盖 user 手选的)
      setSelectedClipIds(prev => {
        const merged = new Set(prev)
        preselected.forEach(id => merged.add(id))
        return Array.from(merged)
      })
    }).catch(e => {
      console.error('preview-match failed:', e)
      setPreviewError(e.response?.data?.detail || e.message)
    }).finally(() => {
      setPreviewLoading(false)
    })
  }, [step, scriptSegments, candidates, targetDuration])  // v2.2.53: deps 已包含全部需要的, 不再 disable

  const loadLibrary = async (source = librarySource) => {
    try {
      const r = await axios.get(`${API_BASE}/mix/clips/library`, { params: { source } })
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

  // v2.2.54: multi-select UX — 全选当前 filter / 反选 / 清空
  const [sortBy, setSortBy] = useState('match')  // 'match' / 'duration' / 'name'
  const [minScore, setMinScore] = useState(0)    // 0-1, 默认 0 全显
  const [matchScoreMap, setMatchScoreMap] = useState({})  // {clip_id: max_match_score}

  // v2.2.54: previews 拿到后填 matchScoreMap (给 sort 用)
  useEffect(() => {
    if (!previews || previews.length === 0) return
    const newMap = { ...matchScoreMap }
    for (const p of previews) {
      for (const tc of p.top_clips || []) {
        const prev = newMap[tc.clip_id] || 0
        if ((tc.match_score || 0) > prev) {
          newMap[tc.clip_id] = tc.match_score
        }
      }
    }
    setMatchScoreMap(newMap)
  }, [previews])

  const candidatesWithScore = candidates.map(c => ({
    ...c,
    match_score: matchScoreMap[c.id] || c.match_score || 0,
  }))

  const visibleClips = candidatesWithScore
    .filter(c => {
      if (librarySource !== 'all' && c.source_type !== librarySource) return false
      if (librarySource !== 'library' && libraryProject !== 'all' && c.source_project_name !== libraryProject) return false
      if (minScore > 0 && (c.match_score || 0) < minScore) return false
      return true
    })

  const visibleClipIds = visibleClips.map(c => c.id)

  const selectAllVisible = () => {
    // 合并: 已有 + 当前可见 (不删已选)
    const merged = Array.from(new Set([...selectedClipIds, ...visibleClipIds]))
    setSelectedClipIds(merged)
  }

  const invertVisible = () => {
    // 反选当前可见: 已是 selected 的取消, 未选的全选
    const newSet = new Set(selectedClipIds)
    for (const id of visibleClipIds) {
      if (newSet.has(id)) newSet.delete(id)
      else newSet.add(id)
    }
    setSelectedClipIds(Array.from(newSet))
  }

  const clearAll = () => {
    setSelectedClipIds([])
  }

  // 排序可见 clips
  const sortedClips = [...visibleClips].sort((a, b) => {
    if (sortBy === 'match') return (b.match_score || 0) - (a.match_score || 0)
    if (sortBy === 'duration') return (b.duration || 0) - (a.duration || 0)
    if (sortBy === 'name') return (a.title || '').localeCompare(b.title || '')
    return 0
  })

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

          {/* v2.2.35: 实时脚本分段预览 — 帮 user 看到 LLM 抽的关键词, 不对可以改 */}
          {(parsingSegments || segmentPreview || segmentParseError) && (
            <div className="segment-preview-box">
              <div className="segment-preview-head">
                <Icon name="list" size={14} />
                <span>实时分段预览 (LLM 抽视觉关键词)</span>
                {parsingSegments && <span className="segment-preview-loading"><Icon name="spinner" size={11} /> 解析中...</span>}
                {segmentPreview && !parsingSegments && (
                  <span className="segment-preview-count">{segmentPreview.length} 段</span>
                )}
              </div>
              {segmentParseError && (
                <div className="segment-preview-error">
                  <Icon name="warning" size={11} /> 解析失败: {segmentParseError}
                </div>
              )}
              {segmentPreview && segmentPreview.length > 0 && (
                <div className="segment-preview-list">
                  {segmentPreview.map((seg, i) => (
                    <div key={i} className="segment-preview-item">
                      <div className="segment-preview-pos">{i + 1}</div>
                      <div className="segment-preview-body">
                        <div className="segment-preview-text">{seg.text}</div>
                        {seg.keywords && seg.keywords.length > 0 && (
                          <div className="segment-preview-keywords">
                            {seg.keywords.map((kw, j) => (
                              <span key={j} className="segment-keyword-tag">{kw}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  <div className="segment-preview-tip">
                    关键词会用来从资源库匹配画面 (v2.2.33 视觉匹配).
                    如果关键词偏向"主题/概念" (如"防水/品质"), 改写脚本强调"画面/视觉" (如"屋顶/瓦片/雨").
                  </div>
                </div>
              )}
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
            <p className="wizard-hint">从切片项目 / 资源库勾选素材（{selectedClipIds.length} 已选）</p>
          </div>

          {/* v2.2.41: 按段预选 — 每段显示 top-3 候选, 自动勾选 top-1 */}
          {(previewLoading || previewError || previews) && scriptSegments && scriptSegments.length > 0 && (
            <div className="segment-preselect-box">
              <div className="segment-preselect-head" onClick={() => setShowSegments(!showSegments)} style={{ cursor: 'pointer' }}>
                <Icon name={showSegments ? 'chevronDown' : 'chevronRight'} size={12} />
                <span>按段预选（v2.2.41 视觉匹配）</span>
                {previewLoading && <span className="segment-preselect-loading"><Icon name="spinner" size={11} /> 计算中...</span>}
                {previews && !previewLoading && (
                  <span className="segment-preselect-count">{previews.length} 段 · 自动预选 {previews.filter(p => p.top_clips.length > 0).length} 个</span>
                )}
                <button
                  type="button"
                  className="segment-preselect-toggle"
                  onClick={(e) => { e.stopPropagation(); setShowSegments(!showSegments) }}
                  style={{ marginLeft: 'auto' }}
                >
                  {showSegments ? '折叠' : '展开'}
                </button>
              </div>
              {previewError && (
                <div className="segment-preselect-error">
                  <Icon name="warning" size={11} /> 预选失败: {previewError}
                </div>
              )}
              {showSegments && previews && previews.length > 0 && (
                <div className="segment-preselect-list">
                  {previews.map((p) => (
                    <div key={p.position} className="segment-preselect-item">
                      <div className="segment-preselect-pos">{p.position + 1}</div>
                      <div className="segment-preselect-body">
                        <div className="segment-preselect-text">{p.text}</div>
                        {p.keywords && p.keywords.length > 0 && (
                          <div className="segment-preselect-keywords">
                            {p.keywords.map((kw, j) => (
                              <span key={j} className="segment-preselect-keyword">{kw}</span>
                            ))}
                          </div>
                        )}
                        {p.top_clips.length === 0 ? (
                          <div className="segment-preselect-empty">该段无匹配素材, 提交时会用 fallback 占位</div>
                        ) : (
                          <div className="segment-preselect-top-clips">
                            {p.top_clips.map((tc, j) => {
                              const selected = selectedClipIds.includes(tc.clip_id)
                              return (
                                <div
                                  key={tc.clip_id}
                                  className={`segment-preselect-thumb ${selected ? 'selected' : ''} ${j === 0 ? 'top1' : ''}`}
                                  onClick={() => toggleClip(tc.clip_id)}
                                  title={`${tc.title} (匹配分 ${(tc.match_score * 100).toFixed(0)}% · 命中: ${tc.matched_keywords.join(', ')})`}
                                >
                                  {selected && <div className="segment-preselect-check"><Icon name="check" size={12} /></div>}
                                  {j === 0 && <div className="segment-preselect-rank">top-1</div>}
                                  <div className="segment-preselect-thumb-score">{(tc.match_score * 100).toFixed(0)}%</div>
                                  <div className="segment-preselect-thumb-title">{tc.title || '(未命名)'}</div>
                                  <div className="segment-preselect-thumb-keywords">
                                    {tc.matched_keywords.slice(0, 3).map((kw, k) => (
                                      <span key={k} className="segment-preselect-hit">{kw}</span>
                                    ))}
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* v2.2.54: multi-select toolbar (全选 / 反选 / 清空 + 排序 + 最低分) */}
          <div className="multi-select-toolbar">
            <div className="multi-select-toolbar-left">
              <button type="button" className="btn-mini" onClick={selectAllVisible} title="选中所有当前 filter 的素材 (不删已选)">
                <Icon name="checkSquare" size={11} /> 全选 ({visibleClipIds.length})
              </button>
              <button type="button" className="btn-mini" onClick={invertVisible} title="反选当前 filter">
                <Icon name="refresh" size={11} /> 反选
              </button>
              <button type="button" className="btn-mini btn-mini-danger" onClick={clearAll} disabled={selectedClipIds.length === 0} title="清空所有已选">
                <Icon name="trash" size={11} /> 清空 ({selectedClipIds.length})
              </button>
            </div>
            <div className="multi-select-toolbar-right">
              <label className="sort-label">
                排序
                <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="sort-select">
                  <option value="match">匹配分</option>
                  <option value="duration">时长</option>
                  <option value="name">名称</option>
                </select>
              </label>
              <label className="sort-label">
                最低分
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={minScore}
                  onChange={(e) => setMinScore(parseFloat(e.target.value))}
                  className="sort-range"
                />
                <span className="sort-range-value">{(minScore * 100).toFixed(0)}%</span>
              </label>
            </div>
          </div>

          {/* v2.2.5: 第一层 source 切换 — 切片项目 / 资源库 */}
          <div className="tabs">
            <button
              className={`tab ${librarySource === 'all' ? 'tab-active' : ''}`}
              onClick={() => { setLibrarySource('all'); setLibraryProject('all') }}
            >
              <Icon name="layers" size={11} style={{ verticalAlign: '-1px', marginRight: 4 }} />
              全部 ({candidates.filter(c => c.source_type !== 'library').length}+{candidates.filter(c => c.source_type === 'library').length})
            </button>
            <button
              className={`tab ${librarySource === 'project' ? 'tab-active' : ''}`}
              onClick={() => { setLibrarySource('project'); setLibraryProject('all') }}
            >
              <Icon name="scissors" size={11} style={{ verticalAlign: '-1px', marginRight: 4 }} />
              切片库
            </button>
            <button
              className={`tab ${librarySource === 'library' ? 'tab-active' : ''}`}
              onClick={() => { setLibrarySource('library'); setLibraryProject('all') }}
            >
              <Icon name="database" size={11} style={{ verticalAlign: '-1px', marginRight: 4 }} />
              资源库
            </button>
          </div>

          {/* 第二层 — 按项目/标签分组 (跟 source 联动) */}
          {librarySource !== 'library' && (
            <div className="tabs">
              <button
                className={`tab ${libraryProject === 'all' ? 'tab-active' : ''}`}
                onClick={() => setLibraryProject('all')}
              >
                全部 ({candidates.filter(c => librarySource === 'all' || c.source_type === librarySource).length})
              </button>
              {/* 按 source_project_name 分组 */}
              {Array.from(new Set(
                candidates
                  .filter(c => librarySource === 'all' || c.source_type === librarySource)
                  .map(c => c.source_project_name)
                  .filter(Boolean)
              )).map(pname => (
                <button
                  key={pname}
                  className={`tab ${libraryProject === pname ? 'tab-active' : ''}`}
                  onClick={() => setLibraryProject(pname)}
                >
                  {pname.slice(0, 18)} ({candidates.filter(c => c.source_project_name === pname && (librarySource === 'all' || c.source_type === librarySource)).length})
                </button>
              ))}
            </div>
          )}

          <div className="library-grid">
            {sortedClips.map(c => {
                const selected = selectedClipIds.includes(c.id)
                const matchPct = ((c.match_score || 0) * 100).toFixed(0)
                return (
                  <div
                    key={c.id}
                    className={`library-card ${selected ? 'selected' : ''} ${c.match_score > 0.5 ? 'high-match' : ''}`}
                    onClick={() => toggleClip(c.id)}
                  >
                    {selected && <div className="library-card-check"><Icon name="check" size={14} /></div>}
                    {/* v2.2.5: 资源库卡显示 thumbnail, 切片项目卡继续纯文字 */}
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
                    <div className="library-card-title">{c.title || '(未命名片段)'}</div>
                    <div className="library-card-sub">
                      <span>{c.source_project_name}</span>
                      {c.duration && <span>· {formatTC(c.duration)}</span>}
                      {c.match_score > 0 && (
                        <span className={`library-match-score ${c.match_score > 0.5 ? 'high' : 'low'}`}>
                          · 匹配 {matchPct}%
                        </span>
                      )}
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