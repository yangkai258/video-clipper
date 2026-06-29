import Icon from '../Icon'
import { formatTC, formatDate } from '../projectView'

// ponytail: 回收站视图 - content-header + reel-list (trash rows)
// 4 个 handler 全部从 App 传入
export default function TrashView({
  trashProjects,
  onPurgeAll,
  onPurgeOld,
  onRestore,
  onPermanentDelete,
}) {
  if (trashProjects.length === 0) {
    return (
      <div className="empty">
        <div className="empty-icon"><Icon name="trash" size={32} /></div>
        <div className="empty-title">回收站是空的</div>
        <div className="empty-hint">删除的项目会在这里，30 天内可恢复</div>
      </div>
    )
  }
  return (
    <>
      <div className="content-header">
        <div>
          <div className="content-title">回收站</div>
          <div className="content-subtitle">
            {trashProjects.length} 个已删除项目 · 30 天后自动清理
          </div>
        </div>
        <div className="content-actions">
          <button className="btn btn-ghost btn-sm btn-danger" onClick={onPurgeAll} disabled={trashProjects.length === 0}>
            清空回收站
          </button>
          <button className="btn btn-ghost btn-sm" onClick={onPurgeOld}>
            清 30 天前的
          </button>
        </div>
      </div>
      <div className="reel-list">
        {trashProjects.map(p => (
          <div key={p.id} className="reel-row" data-status="deleted" style={{ opacity: 0.7 }}>
            <div className="reel-status-dot" />
            <div className="reel-name">{p.name}</div>
            <span className="status-pill" data-status="deleted">已删除</span>
            <div className="reel-cell">{formatTC(p.video_duration)}</div>
            <div className="reel-cell">{p.clip_count || 0} 个切片</div>
            <div className="reel-cell" style={{ fontSize: 'var(--text-xs)' }}>
              {p.deleted_at ? formatDate(p.deleted_at) : '—'}
            </div>
            <div className="reel-actions" onClick={e => e.stopPropagation()}>
              <button className="btn btn-ghost btn-sm" onClick={() => onRestore(p.id)}>↻ 恢复</button>
              <button className="btn btn-ghost btn-sm btn-danger" onClick={() => onPermanentDelete(p.id, p.name)}>永久删除</button>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
