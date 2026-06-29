import { useState } from 'react'
import Icon from '../Icon'
import { API_BASE, getOrientation } from '../projectView'

export default function ClipCard({ clip, index, projectId, withSubtitle }) {
  const [playing, setPlaying] = useState(false)
  const [errored, setErrored] = useState(false)
  const videoSrc = `${API_BASE}/projects/${projectId}/files/${encodeURIComponent(clip.video_path)}`
  const srtSrc = `${API_BASE}/projects/${projectId}/files/${encodeURIComponent('metadata/input.srt')}`
  // 用 clip 文件名派生缩略图 key
  const clipStem = clip.video_path ? clip.video_path.split('/').pop().replace(/\.mp4$/i, '') : null
  const thumbSrc = clipStem
    ? `/api/v1/clip-thumbs/${projectId}/${encodeURIComponent(clipStem)}.jpg`
    : `/api/v1/thumbnails/${projectId}.jpg`
  // v2.1.26: 按 orientation 选容器
  const orientation = getOrientation(clip.width, clip.height)
  return (
    <div className="pda-clip">
      <div className="pda-clip-thumb" data-orientation={orientation}>
        {playing ? (
          <video controls autoPlay className="pda-clip-video" src={videoSrc}>
            {!withSubtitle && (
              <track label="中文" kind="subtitles" srclang="zh" src={srtSrc} default />
            )}
          </video>
        ) : (
          <button className="pda-clip-poster" onClick={() => setPlaying(true)} title="点击播放">
            <img
              src={thumbSrc}
              alt={clip.title || `片段 ${index + 1}`}
              loading="lazy"
              onError={(e) => {
                if (!errored) { setErrored(true); e.currentTarget.src = `/api/v1/thumbnails/${projectId}.jpg` }
              }}
            />
            <div className="pda-clip-poster-overlay">
              <div className="pda-clip-play-btn"><Icon name="play" size={16} /></div>
              <div className="pda-clip-duration">{(clip.duration || 0).toFixed(1)} 秒</div>
            </div>
          </button>
        )}
      </div>
      <div className="pda-clip-body">
        <div className="pda-clip-title" title={clip.title}>{clip.title || `片段 ${index + 1}`}</div>
        <div className="pda-clip-meta">
          <span className="mono"><Icon name="clock" size={10} style={{ verticalAlign: '-1px', marginRight: 2 }} />{formatTime(clip.start_time)} – {formatTime(clip.end_time)}</span>
          <span className="mono"><Icon name="star" size={10} style={{ verticalAlign: '-1px', marginRight: 2 }} />{clip.score?.toFixed(2) || '—'}</span>
          {/* v2.1.30: 按片下载按钮 */}
          <a
            className="pda-clip-download"
            href={videoSrc}
            download={clip.video_path ? clip.video_path.split('/').pop() : `clip_${index + 1}.mp4`}
            title="下载本片"
             onClick={(e) => e.stopPropagation()}
           ><Icon name="download" size={12} /></a>
        </div>
      </div>
    </div>
  )
}
