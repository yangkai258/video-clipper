import Icon from '../Icon'
import { getOrientation, orientationLabel, formatTC, formatDate, statusLabel } from '../projectView'
import Row from './Row'
import Section from './Section'

export default function ReportModal({ project, onClose }) {
  if (!project) return null
  const cfg = project.processing_config || {}
  const task = project.task || {}
  const clips = project.clips || []
  const collections = project.collections || []
  const orientation = getOrientation(project.video_width, project.video_height)
  const orientationText = orientationLabel[orientation] || '未知'
  // 总切片文件大小 (从 video_path 推不出 size, 用 clips 数量 + 平均时长估算, 真实数据需要后端加)
  const totalDuration = clips.reduce((sum, c) => sum + (c.duration || 0), 0)
  const avgScore = clips.length > 0 ? clips.reduce((s, c) => s + (c.score || 0), 0) / clips.length : 0
  const elapsedSec = task.started_at && task.completed_at
    ? (new Date(task.completed_at) - new Date(task.started_at)) / 1000
    : null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <span className="modal-title-icon" />
            <span><Icon name="chart" size={14} style={{ verticalAlign: '-2px', marginRight: 4 }} />{project.name} · 详细报告</span>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} title="关闭"><Icon name="x" size={12} /></button>
        </div>
        <div className="modal-body">
          {/* === 1. 项目信息 === */}
          <Section title="项目信息" icon="list">
            <Row label="项目 ID" value={<span className="mono">{project.id}</span>} />
            <Row label="项目名称" value={project.name} />
            <Row label="状态" value={<span className="status-pill" data-status={project.status}>{statusLabel[project.status] || project.status}</span>} />
            <Row label="创建时间" value={formatDate(project.created_at)} />
            <Row label="完成时间" value={formatDate(project.completed_at)} />
            {project.description && <Row label="描述" value={project.description} />}
          </Section>

          {/* === 2. 视频信息 === */}
          <Section title="视频元数据" icon="film">
            <Row label="文件路径" value={<span className="mono" style={{ fontSize: 'var(--text-xs)' }}>{project.video_path || '—'}</span>} />
            <Row label="文件大小" value={project.video_size ? `${(project.video_size / 1024 / 1024).toFixed(1)} MB` : '—'} />
            <Row label="时长" value={project.video_duration ? formatTC(project.video_duration) : '—'} />
            <Row label="分辨率" value={project.video_width && project.video_height ? `${project.video_width} × ${project.video_height} (${orientationText})` : '—'} />
            <Row label="字幕文件" value={<span className="mono" style={{ fontSize: 'var(--text-xs)' }}>{project.subtitle_path || '—'}</span>} />
            <Row label="字幕生成" value={project.subtitle_method || '—'} />
          </Section>

          {/* === 3. 处理参数 === */}
          <Section title="处理参数" icon="settings">
            <Row label="风格" value={project.style_name || project.style_id || '默认'} />
            <Row label="目标时长" value={cfg.target_duration ? `${cfg.target_duration} 秒/片` : '—'} />
            <Row label="最大切片数" value={cfg.max_clips ? `≤ ${cfg.max_clips} 片` : '—'} />
            <Row label="字幕烧录" value={cfg.with_subtitle !== false ? <><Icon name="check" size={11} style={{ verticalAlign: '-1px', marginRight: 2 }} />烧录到视频</> : <><Icon name="close" size={11} style={{ verticalAlign: '-1px', marginRight: 2 }} />不烧录</>} />
            <Row label="输出格式" value={
              cfg.output_format === '9:16-letterbox' ? '9:16 上下黑边' :
              cfg.output_format === '9:16-smart-crop' ? '9:16 智能裁剪' :
              '保持原比例'
            } />
            <Row label="处理策略" value={cfg.processing_mode || 'standard'} />
            {cfg.min_score !== undefined && (
              <Row label="最低分阈值" value={`${cfg.min_score}`} />
            )}
          </Section>

          {/* === 4. 任务执行 === */}
          <Section title="任务执行" icon="play">
            <Row label="任务状态" value={task.status || '—'} />
            <Row label="进度" value={task.progress != null ? `${task.progress}% · ${task.current_step || ''}` : '—'} />
            <Row label="开始时间" value={formatDate(task.started_at)} />
            <Row label="完成时间" value={formatDate(task.completed_at)} />
            {elapsedSec && <Row label="实际耗时" value={`${Math.floor(elapsedSec / 60)} 分 ${Math.floor(elapsedSec % 60)} 秒`} />}
            {task.error_message && (
              <Row label="错误信息" value={<span style={{ color: '#ef4444' }}>{task.error_message}</span>} />
            )}
            {task.estimated_remaining && task.status === 'running' && (
              <Row label="预计剩余" value={task.estimated_remaining} />
            )}
          </Section>

          {/* === 5. 输出统计 === */}
          <Section title="输出统计" icon="chart">
            <Row label="切片数" value={`${clips.length} 个`} />
            <Row label="合集数" value={`${collections.length} 个`} />
            <Row label="切片总时长" value={`${totalDuration.toFixed(1)} 秒`} />
            <Row label="平均分" value={avgScore > 0 ? avgScore.toFixed(2) : '—'} />
            {clips.length > 0 && (
              <Row label="最高分" value={
                `${Math.max(...clips.map(c => c.score || 0)).toFixed(2)} · ${
                  (clips.find(c => c.score === Math.max(...clips.map(x => x.score || 0))) || {}).title || ''
                }`
              } />
            )}
          </Section>
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost btn-sm" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  )
}