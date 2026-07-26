import Icon from '../Icon'  // eslint-disable-line no-unused-vars
import { API_BASE } from '../projectView'

export default function SrtTab({ projectId, subtitlePath }) {
  return (
    <div className="pda-srt">
      <div className="pda-srt-info">
        <div><Icon name="tag" size={11} style={{ verticalAlign: '-1px', marginRight: 3 }} />字幕文件 ({subtitlePath || '—'})</div>
        <a className="btn btn-primary btn-sm" href={`${API_BASE}/projects/${projectId}/files/${encodeURIComponent(subtitlePath || '')}`}>下载</a>
      </div>
      <pre className="pda-srt-preview">（字幕预览待加载）</pre>
    </div>
  )
}
