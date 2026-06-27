import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

const API_BASE = '/api/v1'

const EMPTY_FORM = {
  name: '',
  path: '',
  style_id: null,
  with_subtitle: true,
  scan_interval_seconds: 30,
  source_action: 'delete',  // delete | keep | move_done
  enabled: true,
}

export default function WatchFolders() {
  const [folders, setFolders] = useState([])
  const [styles, setStyles] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [editingId, setEditingId] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  const flashSuccess = (msg) => {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(''), 2500)
  }
  const flashError = (msg) => {
    setError(msg)
    setTimeout(() => setError(''), 5000)
  }

  const load = useCallback(async () => {
    try {
      const [w, s] = await Promise.all([
        axios.get(`${API_BASE}/watch-folders`),
        axios.get(`${API_BASE}/styles`),
      ])
      setFolders(w.data.folders || [])
      setStyles(s.data || [])
    } catch (e) {
      console.error(e)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [load])

  const handleSubmit = async () => {
    if (!form.name.trim()) return flashError('请填写显示名称')
    if (!form.path.trim()) return flashError('请填写监控路径')
    if (!form.path.startsWith('/')) return flashError('路径必须是绝对路径（以 / 开头）')

    setBusy(true)
    try {
      if (editingId) {
        await axios.put(`${API_BASE}/watch-folders/${editingId}`, form)
        flashSuccess('已更新')
      } else {
        await axios.post(`${API_BASE}/watch-folders`, form)
        flashSuccess('已创建，扫描会在 30s 内自动触发')
      }
      setShowForm(false)
      setForm(EMPTY_FORM)
      setEditingId(null)
      load()
    } catch (e) {
      flashError(e.response?.data?.detail || e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleEdit = (wf) => {
    setForm({
      name: wf.name,
      path: wf.path,
      style_id: wf.style_id,
      with_subtitle: wf.with_subtitle,
      scan_interval_seconds: wf.scan_interval_seconds,
      source_action: wf.source_action,
      enabled: wf.enabled,
    })
    setEditingId(wf.id)
    setShowForm(true)
  }

  const handleDelete = async (id) => {
    if (!confirm('确定删除这个 watch folder 吗？已处理过的文件不会重复处理。')) return
    try {
      await axios.delete(`${API_BASE}/watch-folders/${id}`)
      flashSuccess('已删除')
      load()
    } catch (e) {
      flashError(e.response?.data?.detail || e.message)
    }
  }

  const handleScanNow = async (id) => {
    try {
      const res = await axios.post(`${API_BASE}/watch-folders/${id}/scan`)
      flashSuccess(res.data.message + ` (新文件 ${res.data.new_files})`)
      load()
    } catch (e) {
      flashError(e.response?.data?.detail || e.message)
    }
  }

  const handleToggle = async (wf) => {
    try {
      await axios.put(`${API_BASE}/watch-folders/${wf.id}`, { ...wf, enabled: !wf.enabled })
      load()
    } catch (e) {
      flashError(e.response?.data?.detail || e.message)
    }
  }

  const fmtTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : '从未'

  return (
    <div className="watch-folders">
      <div className="watch-folders-header">
        <div>
          <h2>📁 Watch Folders</h2>
          <p className="watch-folders-subtitle">
            监控文件夹内的视频自动处理。文件被识别后，根据 source_action 自动删除/保留/移动。
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => {
          setForm(EMPTY_FORM)
          setEditingId(null)
          setShowForm(true)
        }}>
          + 添加监控
        </button>
      </div>

      {error && <div className="alert alert-error">⚠️ {error}</div>}
      {successMsg && <div className="alert alert-success">✓ {successMsg}</div>}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editingId ? '编辑' : '添加'} Watch Folder</h3>
              <button className="modal-close" onClick={() => setShowForm(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-field">
                <label>显示名称 *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="如：直播切片、自动搬运"
                />
              </div>
              <div className="form-field">
                <label>监控路径（绝对路径）*</label>
                <input
                  type="text"
                  value={form.path}
                  onChange={(e) => setForm({ ...form, path: e.target.value })}
                  placeholder="/Users/xxx/Movies/Inbox"
                />
                <small className="form-hint">
                  把视频放到这个目录，系统会自动识别 .mp4/.mov/.avi/.mkv/.webm/.flv/.m4v
                </small>
              </div>
              <div className="form-field">
                <label>处理风格（可选）</label>
                <select
                  value={form.style_id || ''}
                  onChange={(e) => setForm({ ...form, style_id: e.target.value || null })}
                >
                  <option value="">— 默认 —</option>
                  {styles.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <div className="form-field">
                  <label>扫描间隔（秒）</label>
                  <input
                    type="number"
                    min="10"
                    value={form.scan_interval_seconds}
                    onChange={(e) => setForm({ ...form, scan_interval_seconds: parseInt(e.target.value) || 30 })}
                  />
                </div>
                <div className="form-field">
                  <label>源文件处理</label>
                  <select
                    value={form.source_action}
                    onChange={(e) => setForm({ ...form, source_action: e.target.value })}
                  >
                    <option value="delete">处理后删除（推荐）</option>
                    <option value="keep">保留原文件</option>
                    <option value="move_done">移动到 done/ 子目录</option>
                  </select>
                </div>
              </div>
              <div className="form-field form-field-row">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={form.with_subtitle}
                    onChange={(e) => setForm({ ...form, with_subtitle: e.target.checked })}
                  />
                  <span>生成并烧录字幕</span>
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                  />
                  <span>启用监控</span>
                </label>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setShowForm(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleSubmit} disabled={busy}>
                {busy ? '保存中...' : (editingId ? '更新' : '创建')}
              </button>
            </div>
          </div>
        </div>
      )}

      {folders.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📁</div>
          <p>还没有监控文件夹</p>
          <p className="empty-hint">点击右上角"添加监控"开始</p>
        </div>
      ) : (
        <div className="watch-folder-list">
          {folders.map(wf => (
            <div key={wf.id} className={`watch-folder-card ${!wf.enabled ? 'disabled' : ''}`}>
              <div className="watch-folder-card-header">
                <div className="watch-folder-name-row">
                  <span className="watch-folder-name">{wf.name}</span>
                  <span className={`badge ${wf.enabled ? 'badge-success' : 'badge-muted'}`}>
                    {wf.enabled ? '运行中' : '已停用'}
                  </span>
                </div>
                <div className="watch-folder-path">{wf.path}</div>
              </div>

              <div className="watch-folder-stats">
                <div className="stat">
                  <div className="stat-label">扫描间隔</div>
                  <div className="stat-value">{wf.scan_interval_seconds}s</div>
                </div>
                <div className="stat">
                  <div className="stat-label">最近扫描</div>
                  <div className="stat-value">{fmtTime(wf.last_scan_at)}</div>
                </div>
                <div className="stat">
                  <div className="stat-label">发现文件</div>
                  <div className="stat-value">{wf.last_found_count}</div>
                </div>
                <div className="stat">
                  <div className="stat-label">源文件</div>
                  <div className="stat-value">
                    {wf.source_action === 'delete' && '🗑 自动删除'}
                    {wf.source_action === 'keep' && '🔒 保留'}
                    {wf.source_action === 'move_done' && '↪ 移到 done/'}
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-label">字幕</div>
                  <div className="stat-value">{wf.with_subtitle ? '✓ 开启' : '— 关闭'}</div>
                </div>
              </div>

              <div className="watch-folder-actions">
                <button className="btn btn-sm btn-ghost" onClick={() => handleScanNow(wf.id)}>
                  🔍 立即扫描
                </button>
                <button className="btn btn-sm btn-ghost" onClick={() => handleToggle(wf)}>
                  {wf.enabled ? '⏸ 停用' : '▶ 启用'}
                </button>
                <button className="btn btn-sm btn-ghost" onClick={() => handleEdit(wf)}>
                  ✎ 编辑
                </button>
                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(wf.id)}>
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}