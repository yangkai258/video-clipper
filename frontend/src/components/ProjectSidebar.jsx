import { formatDate } from '../projectView'

export default function ProjectSidebar({ project, task, cfg, elapsedStr }) {
  return (
    <aside className="pda-side">
      <div className="pda-side-card">
        <div className="pda-side-label">处理信息</div>
        <dl className="pda-dl">
          <dt>风格</dt><dd>{project.style_name || '默认'}</dd>
          <dt>目标时长</dt><dd>{cfg.target_duration ? `${cfg.target_duration} 秒/片` : '—'}</dd>
          <dt>最大切片</dt><dd>{cfg.max_clips ? `≤ ${cfg.max_clips} 片` : '—'}</dd>
          <dt>字幕</dt><dd>{cfg.with_subtitle !== false ? '开启' : '关闭'}</dd>
        </dl>
      </div>
      <div className="pda-side-card">
        <div className="pda-side-label">时间</div>
        <dl className="pda-dl">
          <dt>创建</dt><dd>{formatDate(project.created_at)}</dd>
          <dt>开始</dt><dd>{formatDate(task?.started_at) || '—'}</dd>
          <dt>完成</dt><dd>{formatDate(project.completed_at) || '—'}</dd>
          <dt>耗时</dt><dd>{elapsedStr}</dd>
        </dl>
      </div>
    </aside>
  )
}
