import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import Icon from '../Icon'  // eslint-disable-line no-unused-vars
import EmptyState from '../components/EmptyState'  // eslint-disable-line no-unused-vars
import { formatTC, formatDate } from '../projectView'

// 资源库 (v2.2.5)
// 跨项目长期保留的金句片段 + 用户主动上传的素材.
// 数据: GET /api/v1/library → {resources: [...], metrics: {total, upload, from_project}}

const API_BASE = '/api/v1'
const MAX_UPLOAD_BYTES = 200 * 1024 * 1024  // 200 MB — 超大让用户先压缩

export default function LibraryPage() {
  const [resources, setResources] = useState([])
  const [metrics, setMetrics] = useState({ total: 0, upload: 0, from_project: 0 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState('all')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [uploadFileName, setUploadFileName] = useState('')
  const [playingId, setPlayingId] = useState(null)
  const fileInputRef = useRef(null)

  const load = async (q = search, tab = activeTab) => {
    try {
      setLoading(true)
      const params = new URLSearchParams()
      if (q) params.set('search', q)
      if (tab && tab !== 'all') params.set('source_type', tab)
      const r = await axios.get(`${API_BASE}/library?${params.toString()}`)
      setResources(r.data.resources || [])
      setMetrics(r.data.metrics || { total: 0, upload: 0, from_project: 0 })
    } catch (e) {
      console.error('load library failed:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const t = setTimeout(() => load(search, activeTab), 250)
    return () => clearTimeout(t)
  }, [search, activeTab])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''  // 重置, 允许同名重传

    if (file.size > MAX_UPLOAD_BYTES) {
      const sizeMb = (file.size / 1024 / 1024).toFixed(0)
      if (!confirm(`文件 ${sizeMb}MB 超过 200MB, 上传可能很慢, 建议先压缩. 继续上传?`)) {
        return
      }
    }

    setUploading(true)
    setUploadError('')
    setUploadFileName(file.name)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('name', file.name.replace(/\.[^.]+$/, ''))
      await axios.post(`${API_BASE}/library/upload`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 10 * 60 * 1000,
      })
      await load()
    } catch (err) {
      const detail = err.response?.data?.detail || err.message
      setUploadError(typeof detail === 'string' ? detail : JSON.stringify(detail))
    } finally {
      setUploading(false)
      setUploadFileName('')
    }
  }

  const deleteResource = async (id, name, e) => {
    e.stopPropagation()
    if (!confirm(`确定删除资源「${name}」? 文件和缩略图会一并删除.`)) return
    try {
      await axios.delete(`${API_BASE}/library/${id}`)
      load()
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  return (
    <div className="projects-page">
      <div className="hero-row">
        <div className="hero-card">
          <div className="hero-card-icon"><Icon name="database" size={20} /></div>
          <div className="hero-card-body">
            <div className="hero-card-title">资源库</div>
            <div className="hero-card-sub">
              长期保留的金句片段 + 主动上传的素材 — 项目删除不影响这里
            </div>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">资源总数</div>
          <div className="metric-value">{metrics.total}</div>
          <div className="metric-sub">跨项目长期保留</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">主动上传</div>
          <div className="metric-value">{metrics.upload}</div>
          <div className="metric-sub">不走切片流程</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">项目抽取</div>
          <div className="metric-value">{metrics.from_project}</div>
          <div className="metric-sub">金句片段存档</div>
        </div>
      </div>

      <div className="content-header">
        <div className="content-header-left">
          <input
            className="search-input"
            type="text"
            placeholder="搜索资源名 / 描述 / 来源项目..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ width: 280 }}
          />
        </div>
        <div className="content-header-right">
          {uploading ? (
            <div className="library-upload-progress">
              <Icon name="spinner" size={14} />
              上传中: {uploadFileName}
            </div>
          ) : (
            <button
              className="btn btn-primary"
              onClick={() => fileInputRef.current?.click()}
            >
              <Icon name="upload" size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
              上传视频
            </button>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="video/*"
            style={{ display: 'none' }}
            onChange={handleFileSelect}
          />
        </div>
      </div>

      {uploadError && (
        <div className="library-upload-error">
          <Icon name="alert" size={12} /> 上传失败: {uploadError}
          <button className="btn btn-ghost btn-sm" onClick={() => setUploadError('')} style={{ marginLeft: 8 }}>
            关闭
          </button>
        </div>
      )}<div className="tabs">
        {[
          ['all', '全部', metrics.total],
          ['upload', '主动上传', metrics.upload],
          ['from_project', '项目抽取', metrics.from_project],
        ].map(([k, label, n]) => (
          <button
            key={k}
            className={`tab ${activeTab === k ? 'tab-active' : ''}`}
            onClick={() => setActiveTab(k)}
          >
            {label} ({n})
          </button>
        ))}
      </div>

      {loading && resources.length === 0 ? (
        <EmptyState icon={<Icon name="clock" size={32} />} title="加载中..." />
      ) : resources.length === 0 ? (
        <EmptyState
          icon={<Icon name="database" size={32} />}
          title={search || activeTab !== 'all' ? '没有匹配的资源' : '资源库还是空的'}
          hint={search || activeTab !== 'all'
            ? '试试清空搜索或切换 tab'
            : '点击右上角「上传视频」或去切片项目「存入资源库」'}
          action={!search && activeTab === 'all' && (
            <button className="btn btn-primary" onClick={() => fileInputRef.current?.click()}>
              <Icon name="upload" size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />
              上传第一个视频
            </button>
          )}
        />
      ) : (
        <div className="reel-grid">
          {resources.map(r => (
            <ResourceCard
              key={r.id}
              resource={r}
              onPlay={() => setPlayingId(r.id)}
              onDelete={(e) => deleteResource(r.id, r.name, e)}
            />
          ))}
        </div>
      )}

      {playingId && (
        <div className="library-video-modal" onClick={() => setPlayingId(null)}>
          <div className="library-video-modal-inner" onClick={e => e.stopPropagation()}>
            <button className="library-video-modal-close" onClick={() => setPlayingId(null)} title="关闭">
              <Icon name="x" size={18} />
            </button>
            <video
              src={`/api/v1/library/videos/${playingId}`}
              controls
              autoPlay
              style={{ maxWidth: '90vw', maxHeight: '85vh' }}
            />
          </div>
        </div>
      )}
    </div>
  )
}


// 单个资源卡 — 复用 .reel-card, cover 直接 thumbnail img
// eslint-disable-next-line no-unused-vars
function ResourceCard({ resource, onPlay, onDelete }) {
  const r = resource
  return (
    <div className="reel-card" data-status="library" onClick={onPlay}>
      <div className="reel-card-thumb">
        <div className="reel-card-status">
          <span className={`library-source-tag library-source-${r.source_type}`}>
            {r.source_type === 'upload' ? '主动上传' : '项目抽取'}
          </span>
        </div>
        {r.has_video ? (
          <img
            className="reel-card-thumb-img"
            src={`/api/v1/library/thumbnails/${r.id}`}
            alt={r.name}
            loading="lazy"
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
        ) : (
          <div className="reel-card-thumb-icon">
            <Icon name="film" size={28} />
          </div>
        )}
      </div>
      <div className="reel-card-body">
        <div className="reel-card-title" title={r.name}>{r.name || '未命名'}</div>
        <div className="reel-card-meta">
          <span><Icon name="clock" size={10} /> {formatTC(r.duration)}</span>
          <span>· {(r.size / 1024 / 1024).toFixed(1)} MB</span>
          {r.source_project_name && (
            <span title={`来源项目: ${r.source_project_name}`}>
              <Icon name="folder" size={10} /> {r.source_project_name.slice(0, 14)}
            </span>
          )}
        </div>
        <div className="reel-card-meta" style={{ marginTop: 4 }}>
          <span title={formatDate(r.created_at)}>
            <Icon name="clock" size={10} /> {formatDate(r.created_at)}
          </span>
        </div>
        <div className="reel-card-actions" onClick={e => e.stopPropagation()}>
          <button className="btn btn-ghost btn-sm" onClick={onPlay}>
            <Icon name="play" size={11} /> 播放
          </button>
          <button className="btn btn-ghost btn-sm btn-danger" onClick={onDelete}>
            <Icon name="trash" size={11} /> 删除
          </button>
        </div>
      </div>
    </div>
  )
}