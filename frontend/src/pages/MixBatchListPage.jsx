import { useState, useEffect } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'
import Icon from '../Icon'
import EmptyState from '../components/EmptyState'
import { statusLabel, formatTC, formatDate } from '../projectView'

// ponytail: 批量混剪列表 (v2.2.6)
// 数据: GET /api/v1/mix/batch → {batches: [{id, name, status, total_count, completed_count, failed_count, ...}]}

const API_BASE = '/api/v1'

export default function MixBatchListPage() {
  const navigate = useNavigate()
  const [batches, setBatches] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('all')

  const load = async () => {
    try {
      setLoading(true)
      const r = await axios.get(`${API_BASE}/mix/batch`)
      setBatches(r.data.batches || [])
    } catch (e) {
      console.error('load batch list failed:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 5000)  // 5s 轮询, 让 running batch 进度实时刷新
    return () => clearInterval(t)
  }, [])

  const counts = {
    all: batches.length,
    running: batches.filter(b => b.status === 'running' || b.status === 'pending').length,
    completed: batches.filter(b => b.status === 'completed').length,
    partial: batches.filter(b => b.status === 'partial').length,
    failed: batches.filter(b => b.status === 'failed' || b.status === 'cancelled').length,
  }

  const filtered = batches.filter(b => {
    if (activeTab === 'running' && !(b.status === 'running' || b.status === 'pending')) return false
    if (activeTab === 'completed' && b.status !== 'completed') return false
    if (activeTab === 'partial' && b.status !== 'partial') return false
    if (activeTab === 'failed' && !(b.status === 'failed' || b.status === 'cancelled')) return false
    return true
  })

  const deleteBatch = async (id, name, e) => {
    e.stopPropagation()
    if (!confirm(`取消批量「${name}」？未跑的 task 会停止, 已跑的不会中断。`)) return
    try {
      const r = await axios.delete(`${API_BASE}/mix/batch/${id}`)
      alert(`已取消 (revoked ${r.data.revoked_tasks} 个未跑 task)`)
      load()
    } catch (err) {
      alert('取消失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  if (loading && batches.length === 0) {
    return <EmptyState icon={<Icon name="clock" size={32} />} title="加载中..." />
  }

  return (
    <div className="projects-page">
      <div className="hero-row">
        <div className="hero-card">
          <div className="hero-card-icon"><Icon name="layers" size={20} /></div>
          <div className="hero-card-body">
            <div className="hero-card-title">批量混剪</div>
            <div className="hero-card-sub">
              一次性提交多个变体 (A/B 测试 / 多素材组), 默认串行处理 (max_concurrent=1)
            </div>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">批次总数</div>
          <div className="metric-value">{counts.all}</div>
          <div className="metric-sub">{counts.running} 处理中</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">完成率</div>
          <div className="metric-value">
            {batches.length > 0
              ? Math.round((counts.completed / (counts.completed + counts.partial + counts.failed || 1)) * 100)
              : 0}%
          </div>
          <div className="metric-sub">{counts.completed} 全部完成</div>
        </div>
      </div>

      <div className="content-header">
        <div className="content-header-left" />
        <div className="content-header-right">
          <button className="btn btn-primary" onClick={() => navigate('/mix/batch/new')}>
            <Icon name="plus" size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
            新建批量
          </button>
        </div>
      </div>

      <div className="tabs">
        {[
          ['all', '全部', counts.all],
          ['running', '处理中', counts.running],
          ['completed', '完成', counts.completed],
          ['partial', '部分', counts.partial],
          ['failed', '失败/取消', counts.failed],
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

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Icon name="layers" size={32} />}
          title={batches.length === 0 ? '还没有批量任务' : '没有匹配的批量任务'}
          hint={batches.length === 0 ? '点击「新建批量」, 一次性提交多个混剪变体' : '试试其他状态'}
          action={batches.length === 0 && (
            <button className="btn btn-primary" onClick={() => navigate('/mix/batch/new')}>
              <Icon name="plus" size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
              新建批量
            </button>
          )}
        />
      ) : (
        <div className="reel-grid">
          {filtered.map(b => (
            <MixBatchCard key={b.id} batch={b} onDelete={(e) => deleteBatch(b.id, b.name, e)} />
          ))}
        </div>
      )}
    </div>
  )
}


function MixBatchCard({ batch, onDelete }) {
  const navigate = useNavigate()
  const b = batch
  const isRunning = b.status === 'running' || b.status === 'pending'
  const isCompleted = b.status === 'completed'
  const isPartial = b.status === 'partial'
  const progress = b.total_count > 0 ? ((b.completed_count + b.failed_count) / b.total_count) * 100 : 0

  return (
    <div
      className="reel-card"
      data-status={b.status}
      onClick={() => navigate(`/mix/batch/${b.id}`)}
    >
      <div className="reel-card-thumb">
        <div className="reel-card-status">
          <span className="reel-status-dot" data-status={b.status} />
          <span className="status-pill" data-status={b.status}>
            {statusLabel[b.status] || b.status}
          </span>
        </div>
        {/* 进度条覆盖 */}
        <div className="reel-card-progress" title={`${b.completed_count}/${b.total_count} 完成, ${b.failed_count} 失败`}>
          <div className="reel-card-progress-bar">
            <div className="reel-card-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <span className="reel-card-progress-label">{Math.round(progress)}%</span>
        </div>
      </div>
      <div className="reel-card-body">
        <div className="reel-card-title">{b.name}</div>
        <div className="reel-card-meta">
          <span className="style-badge style-badge-default" title="总任务数">
            <Icon name="layers" size={10} /> {b.total_count} 个变体
          </span>
          <span className="subtitle-label subtitle-label-on" title="并发数 (考虑服务器性能)">
            并发 {b.max_concurrent}
          </span>
          <span title={formatDate(b.created_at)}>
            <Icon name="clock" size={10} /> {formatDate(b.created_at)}
          </span>
        </div>
        <div className="reel-card-meta" style={{ marginTop: 4 }}>
          <span className="subtitle-label subtitle-label-on" style={{ background: 'color-mix(in srgb, #10b981 14%, transparent)', color: '#10b981', borderColor: 'color-mix(in srgb, #10b981 30%, transparent)' }}>
            ✓ {b.completed_count}
          </span>
          {b.failed_count > 0 && (
            <span className="reel-card-error-hint" style={{ color: '#ef4444' }}>
              <Icon name="alert" size={10} /> {b.failed_count} 失败
            </span>
          )}
        </div>
        <div className="reel-card-actions" onClick={e => e.stopPropagation()}>
          {isCompleted && (
            <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/mix/batch/${b.id}`)}>
              <Icon name="play" size={11} /> 查看
            </button>
          )}
          {isRunning && (
            <button className="btn btn-ghost btn-sm btn-danger" onClick={onDelete}>
              <Icon name="x" size={11} /> 取消
            </button>
          )}
          {(isPartial || b.status === 'failed') && (
            <button className="btn btn-ghost btn-sm btn-danger" onClick={onDelete}>
              <Icon name="trash" size={11} /> 删除
            </button>
          )}
        </div>
      </div>
    </div>
  )
}