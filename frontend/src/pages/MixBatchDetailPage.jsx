import { useState, useEffect } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'
import Icon from '../Icon'
import EmptyState from '../components/EmptyState'
import Breadcrumb from '../components/Breadcrumb'
import { statusLabel, formatTC, formatDate } from '../projectView'

// ponytail: 批量混剪详情 (v2.2.6)
// 显示: 整体进度 + N 个子项目状态 + 操作
// 数据: GET /api/v1/mix/batch/{id} → {id, name, status, total_count, completed_count, failed_count, projects: [...]}

const API_BASE = '/api/v1'

export default function MixBatchDetailPage({ batchId, navigate: navProp }) {
  const navigate = navProp || useNavigate()
  const id = batchId
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const r = await axios.get(`${API_BASE}/mix/batch/${id}`)
      setData(r.data)
      setError('')
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // 处理中每 3s 轮询
    const t = setInterval(() => {
      if (data?.status === 'running' || data?.status === 'pending') {
        load()
      }
    }, 3000)
    return () => clearInterval(t)
  }, [id])  // eslint-disable-line

  const cancelBatch = async () => {
    if (!confirm(`取消批量「${data?.name}」？未跑的 task 会停止, 已跑的不会中断。`)) return
    try {
      await axios.delete(`${API_BASE}/mix/batch/${id}`)
      load()
    } catch (e) {
      alert('取消失败: ' + (e.response?.data?.detail || e.message))
    }
  }

  if (loading) return <EmptyState icon={<Icon name="clock" size={32} />} title="加载中..." />
  if (error || !data) {
    return (
      <EmptyState
        icon={'∅'}
        title="批次不存在"
        hint={error || '它可能已被删除'}
        action={<button className="btn btn-primary" onClick={() => navigate('/mix/batch')}>返回列表</button>}
      />
    )
  }

  const projects = data.projects || []
  const isRunning = data.status === 'running' || data.status === 'pending'
  const isCompleted = data.status === 'completed'
  const isPartial = data.status === 'partial'
  const totalDone = data.completed_count + data.failed_count
  const progress = data.total_count > 0 ? (totalDone / data.total_count) * 100 : 0

  return (
    <div className="pda-layout">
      <div className="pda-breadcrumb">
        <Breadcrumb
          items={[
            { label: '工作台' },
            { label: '混剪项目', icon: 'layers', onClick: () => navigate('/mix') },
            { label: '批量混剪', icon: 'layers', onClick: () => navigate('/mix/batch') },
            { label: data.name, icon: 'film' },
          ]}
        />
      </div>

      {/* 顶部信息 */}
      <div className="pda-header">
        <div className="pda-cover">
          <div className="mix-cover-completed">
            <Icon name="layers" size={48} />
          </div>
        </div>

        <div className="pda-info">
          <div className="pda-info-top">
            <span className="status-pill" data-status={data.status}>
              {statusLabel[data.status] || data.status}
            </span>
            <span className="mix-tag">批量</span>
            <span className="mix-tag-dim">
              <Icon name="layers" size={11} /> {data.total_count} 个变体
            </span>
            <span className="mix-tag-dim" title="并发数">
              <Icon name="clock" size={11} /> 并发 {data.max_concurrent}
            </span>
          </div>
          <h1 className="pda-title">{data.name}</h1>
          <div className="pda-meta">
            <span><Icon name="clock" size={11} /> {formatDate(data.created_at)}</span>
            {data.completed_at && (
              <>
                <span className="pda-meta-sep">·</span>
                <span>完成 {formatDate(data.completed_at)}</span>
              </>
            )}
          </div>
          <div className="pda-actions">
            {isRunning && (
              <button className="btn btn-ghost btn-sm btn-danger" onClick={cancelBatch}>
                <Icon name="x" size={11} /> 取消批量
              </button>
            )}
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/mix/batch/new')}>
              <Icon name="plus" size={11} /> 新建批量
            </button>
          </div>
        </div>
      </div>

      {/* 整体进度条 */}
      <div className="mix-player-card" style={{ marginTop: 'var(--space-4)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)' }}>
            <Icon name="chart" size={12} /> 整体进度
          </div>
          <div style={{ fontFamily: 'var(--text-mono)', fontWeight: 600, color: 'var(--accent)' }}>
            {Math.round(progress)}%
          </div>
        </div>
        <div className="project-progress-bar" style={{ height: 10 }}>
          <div
            className="project-progress-bar-fill"
            style={{
              width: `${progress}%`,
              background: isPartial ? 'linear-gradient(to right, #10b981, #f59e0b)' : 'var(--accent)',
            }}
          />
        </div>
        <div style={{ display: 'flex', gap: 16, marginTop: 12, fontSize: 'var(--text-sm)' }}>
          <span style={{ color: '#10b981' }}>
            <Icon name="check" size={11} /> 完成 {data.completed_count}
          </span>
          {data.failed_count > 0 && (
            <span style={{ color: '#ef4444' }}>
              <Icon name="alert" size={11} /> 失败 {data.failed_count}
            </span>
          )}
          <span style={{ color: 'var(--text-dim)' }}>
            <Icon name="clock" size={11} /> 处理中 {data.total_count - totalDone}
          </span>
        </div>
      </div>

      {/* 子项目表 */}
      <div className="mix-sources-card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="mix-section-header">
          <Icon name="layers" size={13} />
          <span>变体列表（{projects.length}）</span>
        </div>
        <div className="mix-sources-table">
          <div className="mix-sources-row mix-sources-head">
            <div>#</div>
            <div>变体名</div>
            <div>脚本片段</div>
            <div>进度</div>
            <div>状态</div>
          </div>
          {projects.map((p, i) => (
            <div
              key={p.id}
              className="mix-sources-row"
              style={{ cursor: p.status === 'completed' ? 'pointer' : 'default' }}
              onClick={() => {
                if (p.status === 'completed') {
                  navigate(`/mix/${p.id}`)
                }
              }}
            >
              <div className="mix-sources-pos">{i + 1}</div>
              <div className="mix-sources-title">
                <div className="mix-sources-title-main">{p.name}</div>
                <div className="mix-sources-title-sub">
                  {p.video_duration > 0 ? `${formatTC(p.video_duration)}` : '—'}
                  {p.video_size > 0 && ` · ${(p.video_size / 1024 / 1024).toFixed(1)} MB`}
                </div>
              </div>
              <div className="mix-sources-text">
                {p.task?.current_step || (p.task?.error_message ? p.task.error_message.slice(0, 50) : '—')}
              </div>
              <div className="mix-sources-score">
                <div className="mix-sources-score-bar">
                  <div
                    className="mix-sources-score-fill"
                    style={{ width: `${p.task?.progress || 0}%` }}
                  />
                </div>
                <span>{p.task?.progress || 0}%</span>
              </div>
              <div>
                <span className="status-pill" data-status={p.status} style={{ fontSize: 11, padding: '2px 8px' }}>
                  {statusLabel[p.status] || p.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}