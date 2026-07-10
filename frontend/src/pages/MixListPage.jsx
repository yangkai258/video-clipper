import { useState, useEffect } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'
import Icon from '../Icon'
import EmptyState from '../components/EmptyState'
import { statusLabel, formatTC, formatDate, formatDuration } from '../projectView'

// ponytail: 混剪项目列表 (v2.2.4)
// 跟切片项目列表分离 (不同 db 不同 api), 但 UI 复用 .reel-card 样式
// 数据: GET /api/v1/mix → {projects: [{id, name, status, video_size, video_duration, thumbnail_path, source_clip_count, ...}]}

const API_BASE = '/api/v1'

export default function MixListPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState('all')

  const load = async () => {
    try {
      setLoading(true)
      const r = await axios.get(`${API_BASE}/mix`)
      setProjects(r.data.projects || [])
    } catch (e) {
      console.error('load mix list failed:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // 每 5s 轮询, 让 processing 状态实时刷新
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [])

  const counts = {
    all: projects.length,
    processing: projects.filter(p => p.status === 'processing' || p.status === 'pending').length,
    completed: projects.filter(p => p.status === 'completed').length,
    failed: projects.filter(p => p.status === 'failed').length,
  }

  const filtered = projects.filter(p => {
    // 状态过滤
    if (activeTab === 'processing' && !(p.status === 'processing' || p.status === 'pending')) return false
    if (activeTab === 'completed' && p.status !== 'completed') return false
    if (activeTab === 'failed' && p.status !== 'failed') return false
    // 搜索
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const deleteMix = async (id, name, e) => {
    e.stopPropagation()
    if (!confirm(`确定删除混剪「${name}」？此操作不可恢复。`)) return
    try {
      await axios.delete(`${API_BASE}/mix/${id}`)
      load()
    } catch (err) {
      alert('删除失败：' + (err.response?.data?.detail || err.message))
    }
  }

  if (loading && projects.length === 0) {
    return <EmptyState icon={<Icon name="clock" size={32} />} title="加载中..." />
  }

  return (
    <div className="projects-page">
      {/* v2.2.4: 顶部 hero — 信息卡 + metric + 主操作按钮 */}
      <div className="hero-row">
        <div className="hero-card">
          <div className="hero-card-icon"><Icon name="layers" size={20} /></div>
          <div className="hero-card-body">
            <div className="hero-card-title">混剪项目</div>
            <div className="hero-card-sub">
              上传直播录像后用 AI 自动切片，再用混剪快速产出带货短视频
            </div>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">混剪项目</div>
          <div className="metric-value">{counts.all}</div>
          <div className="metric-sub">{counts.completed} 已完成</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">成功率</div>
          <div className="metric-value">
            {counts.all > 0
              ? Math.round((counts.completed / (counts.completed + counts.failed || 1)) * 100)
              : 0}%
          </div>
          <div className="metric-sub">{counts.failed} 失败</div>
        </div>
      </div>

      {/* 搜索 + 顶部操作 */}
      <div className="content-header">
        <div className="content-header-left">
          <input
            className="search-input"
            type="text"
            placeholder="搜索混剪项目..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ width: 240 }}
          />
        </div>
        <div className="content-header-right">
          <button
            className="btn btn-primary"
            onClick={() => navigate('/mix/new')}
          >
            <Icon name="plus" size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
            新建混剪
          </button>
        </div>
      </div>

      {/* 状态 tab */}
      <div className="tabs">
        {[
          ['all', '全部', counts.all],
          ['processing', '处理中', counts.processing],
          ['completed', '已完成', counts.completed],
          ['failed', '失败', counts.failed],
        ].map(([k, label, n]) => (
          <button
            key={k}
            className={`tab ${activeTab === k ? 'tab-active' : ''}`}
            onClick={() => setActiveTab(k)}
          >
            {label} ({n})
          </button>
        ))}
      </div>

      {/* 列表 / 空态 */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={<Icon name="layers" size={32} />}
          title={projects.length === 0 ? '还没有混剪项目' : '没有匹配的混剪项目'}
          hint={projects.length === 0 ? '点击右上角「新建混剪」开始第一次混剪' : '试试其他状态或清空搜索'}
          action={projects.length === 0 && (
            <button className="btn btn-primary" onClick={() => navigate('/mix/new')}>
              <Icon name="plus" size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
              新建混剪
            </button>
          )}
        />
      ) : (
        <div className="reel-grid">
          {filtered.map(p => (
            <MixProjectCard key={p.id} project={p} onDelete={(e) => deleteMix(p.id, p.name, e)} />
          ))}
        </div>
      )}
    </div>
  )
}


// 单个混剪卡 — 复用 .reel-card 样式 + thumbnail 走 mix endpoint
function MixProjectCard({ project, onDelete }) {
  const navigate = useNavigate()
  const p = project
  const task = p.task || {}
  const isCompleted = p.status === 'completed'

  return (
    <div
      className="reel-card"
      data-status={p.status}
      onClick={() => navigate(`/mix/${p.id}`)}
    >
      <div className="reel-card-thumb">
        <div className="reel-card-status">
          <span className="reel-status-dot" data-status={p.status} />
          <span className="status-pill" data-status={p.status}>
            {statusLabel[p.status] || p.status}
          </span>
        </div>
        {/* 缩略图: 完成的 mix 项目用 thumbnail endpoint */}
        {isCompleted && p.thumbnail_path ? (
          <img
            className="reel-card-thumb-img"
            src={`/api/v1/mix/thumbnails/${p.id}`}
            alt={p.name}
            loading="lazy"
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
        ) : null}
        {p.status === 'processing' && (
          <div className="reel-card-progress" title={task.current_step || `处理中 ${task.progress || 0}%`}>
            <div className="reel-card-progress-bar">
              <div className="reel-card-progress-fill" style={{ width: `${task.progress || 0}%` }} />
            </div>
            <span className="reel-card-progress-label">{task.progress || 0}%</span>
          </div>
        )}
      </div>
      <div className="reel-card-body">
        <div className="reel-card-title">{p.name}</div>
        <div className="reel-card-meta">
          <span className="style-badge style-badge-default" title={`目标时长: ${p.target_duration_seconds || 60}s`}>
            目标 {p.target_duration_seconds || 60}s
          </span>
          {p.source_clip_count > 0 && (
            <span className="subtitle-label subtitle-label-on" title="引用了 N 个切片片段">
              {p.source_clip_count} 段
            </span>
          )}
          <span title={formatDate(p.created_at)}>
            <Icon name="clock" size={10} /> {formatDate(p.created_at)}
          </span>
        </div>
        <div className="reel-card-meta" style={{ marginTop: 4 }}>
          {isCompleted && p.video_size > 0 && (
            <>
              <span><Icon name="film" size={10} /> {formatTC(p.video_duration)}</span>
              <span>· {(p.video_size / 1024 / 1024).toFixed(1)} MB</span>
            </>
          )}
          {p.status === 'failed' && task.error_message && (
            <span className="reel-card-error-hint" title={task.error_message}>
              <Icon name="alert" size={10} /> {task.error_message.slice(0, 30)}
            </span>
          )}
        </div>
        <div className="reel-card-actions" onClick={e => e.stopPropagation()}>
          {p.status === 'completed' && (
            <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/mix/${p.id}`)}>
              <Icon name="play" size={11} /> 播放
            </button>
          )}
          {p.status !== 'processing' && (
            <button className="btn btn-ghost btn-sm btn-danger" onClick={onDelete}>
              <Icon name="trash" size={11} /> 删除
            </button>
          )}
        </div>
      </div>
    </div>
  )
}