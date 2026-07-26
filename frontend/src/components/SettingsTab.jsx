import Icon from '../Icon'
import { getOrientation, orientationLabel } from '../projectView'

const OUTPUT_FORMAT_LABEL = {
  '9:16-letterbox': '9:16 上下黑边 (抖音适配)',
  '9:16-smart-crop': '9:16 智能裁剪 (TODO)',
  'original': '保持原比例',
}

function fmtOutputFormat(fmt) {
  if (!fmt || fmt === 'original') return OUTPUT_FORMAT_LABEL.original
  return OUTPUT_FORMAT_LABEL[fmt] || fmt
}

export default function SettingsTab({ project, cfg }) {
  return (
    <div className="pda-settings">
      <div className="pda-setting-row"><span>风格</span><strong>{project.style_name || '默认'}</strong></div>
      <div className="pda-setting-row"><span>目标时长</span><strong>{cfg.target_duration ? `${cfg.target_duration} 秒/片` : '—'}</strong></div>
      <div className="pda-setting-row"><span>最大切片</span><strong>{cfg.max_clips ? `≤ ${cfg.max_clips} 片` : '—'}</strong></div>
      <div className="pda-setting-row"><span>字幕</span><strong>{cfg.with_subtitle !== false ? '烧录到视频' : '不烧录'}</strong></div>
      <div className="pda-setting-row"><span>处理策略</span><strong>{cfg.processing_mode || 'standard'}</strong></div>
      {/* v2.1.28: 输出格式 — 处理前在上传策略 modal 选定, 切完不可改 */}
      <div className="pda-setting-row">
        <span>输出格式</span>
        <strong style={{ color: cfg.output_format && cfg.output_format !== 'original' ? '#06b6d4' : undefined }}>
          {fmtOutputFormat(cfg.output_format)}
        </strong>
      </div>
      <div style={{ fontSize: '11px', color: 'var(--text-muted, rgba(255,255,255,0.45))', marginTop: '4px' }}>
        <Icon name="info" size={11} style={{ verticalAlign: '-1px', marginRight: 3 }} />输出格式在上传时确定, 切完不可改 (改的话需要重新上传)
      </div>
      {project.video_width && project.video_height && (
        <div className="pda-setting-row">
          <span>视频尺寸</span>
          <strong>{project.video_width}×{project.video_height} ({orientationLabel[getOrientation(project.video_width, project.video_height)]})</strong>
        </div>
      )}
    </div>
  )
}
