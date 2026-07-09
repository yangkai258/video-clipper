import { useState, useEffect } from 'react'
import Icon from '../Icon'
import axios from 'axios'

const API_BASE = '/api/v1'

/**
 * 重新处理弹窗 (v2.2.1+)
 *
 * - 显示当前 project 的 with_subtitle / output_format / style_id / padding
 * - user 可改这些配置 (with_subtitle / output_format / style / padding)
 * - 调 PUT /projects/{id}/config 改 + POST /projects/{id}/rerun 触发完整 pipeline
 * - 复用 raw 视频, 不重传
 *
 * 父组件控制: open + onClose + project (完整 project 数据)
 */
export default function RerunModal({ project, onClose, onDone }) {
  const cfg = project.processing_config || {}
  const [withSubtitle, setWithSubtitle] = useState(cfg.with_subtitle ?? true)
  const [outputFormat, setOutputFormat] = useState(cfg.output_format || 'original')
  const [styleId, setStyleId] = useState(cfg.style_id || '')
  const [prePad, setPrePad] = useState(cfg.pre_padding_seconds ?? 0)
  const [postPad, setPostPad] = useState(cfg.post_padding_seconds ?? 0)
  const [styles, setStyles] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    axios.get(`${API_BASE}/styles`)
      .then(r => setStyles(r.data || []))
      .catch(() => setStyles([]))
  }, [])

  const submit = async () => {
    setBusy(true)
    setErr('')
    try {
      // 1. 改 processing_config (跟 update_project_config 一样, style_id 触发 padding snapshot)
      await axios.put(`${API_BASE}/projects/${project.id}/config`, {
        with_subtitle: withSubtitle,
        output_format: outputFormat,
        style_id: styleId || undefined,
        pre_padding_seconds: Number(prePad) || 0,
        post_padding_seconds: Number(postPad) || 0,
      })
      // 2. 触发 rerun (清 output + 跑 step 1-10, 复用 raw)
      await axios.post(`${API_BASE}/projects/${project.id}/rerun`, {})
      if (onDone) onDone()
      onClose()
    } catch (e) {
      setErr(e.response?.data?.detail || e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-header">
          <div className="modal-title">
            <Icon name="refresh" size={14} style={{ verticalAlign: '-2px', marginRight: 6 }} />
            重新处理 — {project.name}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} title="关闭">
            <Icon name="x" size={12} />
          </button>
        </div>

        <div className="modal-body">
          <div style={{
            padding: 'var(--space-3)', background: 'var(--bg-soft)',
            borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-4)',
            fontSize: 'var(--text-sm)', color: 'var(--text-secondary)'
          }}>
            <Icon name="info" size={12} style={{ verticalAlign: '-1px', marginRight: 4 }} />
            重新处理将复用原视频（需先启用「保留 raw」），跑 step 1-10 全套。
          </div>

          {/* with_subtitle */}
          <div className="toggle-row">
            <div>
              <div className="toggle-info-label">烧录字幕</div>
              <div className="toggle-info-hint">关 = 纯剪（更快）· 开 = 带字幕</div>
            </div>
            <div
              className={`toggle-switch ${withSubtitle ? 'on' : ''}`}
              onClick={() => !busy && setWithSubtitle(!withSubtitle)}
            />
          </div>

          {/* output_format */}
          <div className="toggle-row">
            <div>
              <div className="toggle-info-label">输出格式</div>
              <div className="toggle-info-hint">
                {outputFormat === 'original' ? '保持原比例' : '9:16 上下黑边 (抖音适配)'}
              </div>
            </div>
            <div
              className={`toggle-switch ${outputFormat === '9:16-letterbox' ? 'on' : ''}`}
              onClick={() => !busy && setOutputFormat(outputFormat === '9:16-letterbox' ? 'original' : '9:16-letterbox')}
            />
          </div>

          {/* style 选择 */}
          <div className="form-row" style={{ marginTop: 'var(--space-3)' }}>
            <label className="form-label">风格 (Style)</label>
            <select
              className="form-select"
              value={styleId}
              onChange={e => setStyleId(e.target.value)}
              disabled={busy}
            >
              <option value="">（不指定，使用当前 style）</option>
              {styles.map(s => (
                <option key={s.id} value={s.id}>{s.name}（±{s.pre_padding_seconds || 0}s / +{s.post_padding_seconds || 0}s）</option>
              ))}
            </select>
          </div>

          {/* padding (仅在 style 未指定时生效, 或手动覆盖) */}
          <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
            <div className="form-row" style={{ flex: 1 }}>
              <label className="form-label">前 padding (秒)</label>
              <input
                type="number"
                className="form-input"
                value={prePad}
                onChange={e => setPrePad(e.target.value)}
                step="0.5"
                min="0"
                max="60"
                disabled={busy}
              />
            </div>
            <div className="form-row" style={{ flex: 1 }}>
              <label className="form-label">后 padding (秒)</label>
              <input
                type="number"
                className="form-input"
                value={postPad}
                onChange={e => setPostPad(e.target.value)}
                step="0.5"
                min="0"
                max="60"
                disabled={busy}
              />
            </div>
          </div>

          {err && (
            <div style={{
              marginTop: 'var(--space-3)', padding: 'var(--space-3)',
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 'var(--radius-sm)', color: '#ef4444', fontSize: 'var(--text-sm)'
            }}>
              <Icon name="alert" size={12} style={{ verticalAlign: '-1px', marginRight: 4 }} />
              {err}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>取消</button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? '处理中…' : '确认重新处理'}
          </button>
        </div>
      </div>
    </div>
  )
}
