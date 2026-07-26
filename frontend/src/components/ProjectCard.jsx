import { useNavigate } from 'react-router-dom'
import Icon from '../Icon'
import { statusLabel, formatTC, formatDate, formatDuration } from '../projectView'

// ponytail: 项目卡 (reel-card) 封装项目展示 + 三个动作按钮
// onStart/onDelete 由 App 注入 (处理 / 删除) - 避免在组件里直接 import hooks
export default function ProjectCard({ project, onStart, onDelete, onSaveToLibrary }) {
  const navigate = useNavigate()
  const p = project
  const orientation = p.orientation  // 上游计算过的, 默认 landscape
  const hasSubtitle = p.has_subtitle
  // v2.2.40: 列表卡片"存到资源库"按钮 — 完成项目 + 有切片才能存
  const canSaveToLibrary = p.status === 'completed' && (p.clip_count || 0) > 0

  return (
    <div
      className="reel-card"
      data-status={p.status}
      onClick={() => navigate(`/project/${p.id}`)}
    >
      <div className="reel-card-thumb">
        <div className="reel-card-status">
          <span className="reel-status-dot" data-status={p.status} />
          <span className="status-pill" data-status={p.status}>{statusLabel[p.status] || p.status}</span>
        </div>
        {/* 封面图: 已完成项目尝试加载第一片抽帧, 失败 fallback */}
        {p.status === 'completed' ? (
          <img
            className="reel-card-thumb-img"
            src={`/api/v1/thumbnails/${p.id}.jpg`}
            alt={p.name}
            loading="lazy"
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
        ) : null}
        {p.status === 'processing' && (
          <div className="reel-card-progress" title={p.current_step || `处理中 ${p.progress || 0}%`}>
            <div className="reel-card-progress-bar">
              <div className="reel-card-progress-fill" style={{ width: `${p.progress || 0}%` }} />
            </div>
            <span className="reel-card-progress-label">{p.progress || 0}%</span>
          </div>
        )}
        {p.status === 'processing' && p.timing && (
          <div className="reel-card-timing">
            <span className="reel-card-timing-elapsed" title="已用时间">
              <Icon name="clock" size={11} style={{ verticalAlign: '-2px', marginRight: 2 }} /> {formatDuration(p.timing.elapsed_seconds)}
            </span>
            {p.timing.eta_seconds != null && p.timing.eta_seconds > 0 && (
              <span className="reel-card-timing-eta" title="预计剩余">
                · 剩 {formatDuration(p.timing.eta_seconds)}
              </span>
            )}
            {p.timing.total_estimated_seconds != null && p.timing.total_estimated_seconds > 0 && (
              <span className="reel-card-timing-total" title="预计总耗时">
                / {formatDuration(p.timing.total_estimated_seconds)}
              </span>
            )}
          </div>
        )}
      </div>
      <div className="reel-card-body">
        <div className="reel-card-title">{p.name}</div>
        <div className="reel-card-meta">
          <span
            className={`style-badge ${p.style_id === '_default' ? 'style-badge-default' : ''}`}
            title={
              p.target_duration || p.max_clips
                ? `${p.style_name || '默认'} · ${p.target_duration || '?'}s/片 · ≤${p.max_clips || '?'}片`
                : undefined
            }
          >
            {p.style_name || '默认'}
          </span>
          <span className={`subtitle-pill ${hasSubtitle ? 'subtitle-pill-on' : 'subtitle-pill-off'}`}>
            <span className="subtitle-pill-icon"><Icon name="tag" size={10} /></span>
          </span>
        </div>
        <div className="reel-card-stats">
          <div className="reel-card-stat">
            <span className="reel-card-stat-value">{formatTC(p.video_duration)}</span>
            <span className="reel-card-stat-label">时长</span>
          </div>
          <div className="reel-card-stat">
            <span className="reel-card-stat-value">{p.clip_count || 0}</span>
            <span className="reel-card-stat-label">切片</span>
          </div>
          <div className="reel-card-stat">
            <span className="reel-card-stat-value">{formatDate(p.created_at)}</span>
            <span className="reel-card-stat-label">创建</span>
          </div>
        </div>
        <div className="reel-card-actions" onClick={e => e.stopPropagation()}>
          {p.status === 'pending' && (
            <button className="btn btn-primary btn-sm" onClick={() => onStart && onStart(p.id)}>处理</button>
          )}
          {/* v2.2.40: 列表卡片快捷"存到资源库" — 不进 ProjectDetail 也能批量加 */}
          {canSaveToLibrary && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => onSaveToLibrary && onSaveToLibrary(p)}
              title="把这个项目所有切片批量加到资源库"
            >
              存到资源库
            </button>
          )}
          <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/project/${p.id}`)}>打开</button>
          <button className="btn btn-ghost btn-sm btn-danger" onClick={() => onDelete && onDelete(p.id, p.name)} title="删除">删除</button>
        </div>
      </div>
    </div>
  )
}
