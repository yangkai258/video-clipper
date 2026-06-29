export default function ProjectProgressCard({ task }) {
  return (
    <div className="pda-progress-card">
      <div className="pda-progress-step">{task.current_step || '处理中...'}</div>
      <div className="pda-progress">
        <div className="pda-progress-bar">
          <div className="pda-progress-fill" style={{ width: `${task.progress || 0}%` }} />
        </div>
        <span className="pda-progress-label">{task.progress || 0}%</span>
      </div>
      <div className="pda-progress-timing">
        {task.elapsed_seconds != null && <span>已用 <strong>{Math.round(task.elapsed_seconds / 60)} 分钟</strong></span>}
        {task.eta_seconds != null && <span>剩余 <strong>{Math.round(task.eta_seconds / 60)} 分钟</strong></span>}
        {task.total_estimated_seconds != null && <span>预计共 <strong>{Math.round(task.total_estimated_seconds / 60)} 分钟</strong></span>}
      </div>
    </div>
  )
}
