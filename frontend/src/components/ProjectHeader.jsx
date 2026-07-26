import Icon from '../Icon'
import { getOrientation, orientationLabel } from '../projectView'

// ponytail: 顶部 cover + 标题 + 主操作栏;start/delete 通过 props 注入
export default function ProjectHeader({ project, onStart, onShowReport, onDelete, onRerun, onSaveAllToLibrary }) {
  const orientation = getOrientation(project.video_width, project.video_height)
  const coverClass = `pda-cover pda-cover-${orientation}`
  const coverTitle = `${orientationLabel[orientation] || ''} ${project.video_width || '?'}×${project.video_height || '?'}`
  const isCompleted = project.status === 'completed'

  const cover = isCompleted ? (
    <div className={coverClass} title={coverTitle}>
      <img
        className="pda-cover-img"
        src={`/api/v1/thumbnails/${project.id}.jpg`}
        alt={project.name}
        onError={(e) => { e.currentTarget.style.display = 'none' }}
      />
      <div className="pda-cover-play"><Icon name="play" size={20} /></div>
    </div>
  ) : (
    <div className={`${coverClass} pda-cover-placeholder`} title={coverTitle}>
      <div className="pda-cover-icon">
        <Icon name={project.status === 'failed' ? 'alert' : project.status === 'processing' ? 'clock' : 'film'} size={48} />
      </div>
    </div>
  )

  return (
    <div className="pda-header">
      {cover}
      <div className="pda-info">
        <div className="pda-info-top">
          <span className="status-pill" data-status={project.status}>{project.statusLabel || project.status}</span>
        </div>
        <h1 className="pda-title">{project.name}</h1>
        <div className="pda-meta">
          <span><Icon name="clock" size={11} style={{ verticalAlign: '-2px', marginRight: 3 }} />{project.formattedDuration || '—'}</span>
          <span className="pda-meta-sep">·</span>
          <span><Icon name="folder" size={11} style={{ verticalAlign: '-2px', marginRight: 3 }} />{project.formattedSize || '—'}</span>
          <span className="pda-meta-sep">·</span>
          <span><Icon name="chart" size={11} style={{ verticalAlign: '-2px', marginRight: 3 }} />{project.formattedCreatedAt || '—'}</span>
        </div>
        <div className="pda-actions">
          {project.status === 'pending' && (
            <button className="btn btn-primary" onClick={onStart}>开始处理</button>
          )}
          {isCompleted && (
            <button className="btn btn-primary btn-sm">播放预览</button>
          )}
          {/* v2.2.1: 重新处理按钮 (复用 raw, 改 with_subtitle/output_format/style/padding) */}
          {(project.status === 'completed' || project.status === 'failed') && onRerun && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={onRerun}
              title="复用原视频重新处理（需先启用「保留 raw」）"
            >
              <Icon name="refresh" size={11} style={{ verticalAlign: '-2px', marginRight: 3 }} />重新处理
            </button>
          )}
          {/* v2.2.5: 一键存全部到资源库 (completed 项目才允许批量, clip 已生成) */}
          {project.status === 'completed' && onSaveAllToLibrary && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={onSaveAllToLibrary}
              title="把本项目所有 clip 复制到资源库 (跨项目长期保留)"
            >
              <Icon name="database" size={11} style={{ verticalAlign: '-2px', marginRight: 3 }} />一键存全部
            </button>
          )}
          <button className="btn btn-ghost btn-sm" onClick={onShowReport}><Icon name="chart" size={11} style={{ verticalAlign: '-2px', marginRight: 3 }} />查看报告</button>
          <button className="btn btn-ghost btn-sm"><Icon name="download" size={11} style={{ verticalAlign: '-2px', marginRight: 3 }} />下载 SRT</button>
          <button className="btn btn-ghost btn-sm btn-danger" onClick={onDelete}><Icon name="x" size={11} style={{ verticalAlign: '-2px', marginRight: 3 }} />删除</button>
        </div>
      </div>
    </div>
  )
}
