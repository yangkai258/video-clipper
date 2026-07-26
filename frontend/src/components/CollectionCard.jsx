import { useState } from 'react'
import Icon from '../Icon'  // eslint-disable-line no-unused-vars
import { API_BASE } from '../projectView'

export default function CollectionCard({ coll, index, projectId }) {
  const [playing, setPlaying] = useState(false)
  const videoSrc = coll.video_path
    ? `${API_BASE}/projects/${projectId}/files/${encodeURIComponent(coll.video_path)}`
    : null
  return (
    <div className="pda-clip">
      <div className="pda-clip-thumb">
        {!videoSrc ? (
          <div className="pda-clip-empty"><Icon name="warning" size={14} style={{ verticalAlign: '-2px', marginRight: 3 }} />视频文件不存在</div>
        ) : playing ? (
          <video controls autoPlay className="pda-clip-video" src={videoSrc} />
        ) : (
          <button className="pda-clip-poster" onClick={() => setPlaying(true)} title="点击播放">
            <img
              src={`/api/v1/thumbnails/${projectId}.jpg`}
              alt={coll.title || `合集 ${index + 1}`}
              loading="lazy"
            />
            <div className="pda-clip-poster-overlay">
              <div className="pda-clip-play-btn"><Icon name="play" size={16} /></div>
              <div className="pda-clip-duration"><Icon name="film" size={10} style={{ verticalAlign: '-1px', marginRight: 2 }} />{coll.clip_count} 切片</div>
            </div>
          </button>
        )}
      </div>
      <div className="pda-clip-body">
        <div className="pda-clip-title" title={coll.title}>{coll.title || `合集 ${index + 1}`}</div>
        {/* v2.1.30: 合集下载按钮 */}
        {videoSrc && (
          <div className="pda-clip-meta">
            <a
              className="pda-clip-download"
              href={videoSrc}
              download={coll.video_path ? coll.video_path.split('/').pop() : `collection_${index + 1}.mp4`}
              title="下载合集"
              onClick={(e) => e.stopPropagation()}
            ><Icon name="download" size={12} /></a>
          </div>
        )}
      </div>
    </div>
  )
}