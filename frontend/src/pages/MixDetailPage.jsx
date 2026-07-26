import { useState, useEffect } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'
import Icon from '../Icon'
import EmptyState from '../components/EmptyState'
import Breadcrumb from '../components/Breadcrumb'
import { statusLabel, formatTC, formatDate } from '../projectView'

// ponytail: 混剪项目详情 (v2.2.4)
// 显示: 视频 player + 脚本预览 + 来源片段表 + 操作按钮
// 数据: GET /api/v1/mix/{id} → {project, source_clips[], task}
// 视频: GET /api/v1/mix/videos/{id}

const API_BASE = '/api/v1'

export default function MixDetailPage({ projectId, navigate: navProp }) {
  // 必须在所有 state 之前无条件 hook,避免 hooks 顺序违规
  const _navHook = useNavigate()
  const navigate = navProp || _navHook
  const id = projectId
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const r = await axios.get(`${API_BASE}/mix/${id}`)
      setData(r.data)
      setError('')
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // 处理中每 3s 轮询
    const t = setInterval(() => {
      if (data?.project?.status === 'processing' || data?.project?.status === 'pending') {
        load()
      }
    }, 3000)
    return () => clearInterval(t)
  }, [id])  // eslint-disable-line

  const deleteProject = async () => {
    if (!confirm(`确定删除混剪「${data?.project?.name}」？`)) return
    try {
      await axios.delete(`${API_BASE}/mix/${id}`)
      navigate('/mix')
    } catch (e) {
      alert('删除失败：' + (e.response?.data?.detail || e.message))
    }
  }

  if (loading) {
    return <EmptyState icon={<Icon name="clock" size={32} />} title="加载中..." />
  }
  if (error || !data) {
    return (
      <EmptyState
        icon={'∅'}
        title="混剪项目不存在"
        hint={error || '它可能已被删除'}
        action={<button className="btn btn-primary" style={{ marginTop: 'var(--space-3)' }} onClick={() => navigate('/mix')}>返回列表</button>}
      />
    )
  }

  const project = data
  const source_clips = data.source_clips || []
  const task = data.task
  const isCompleted = project.status === 'completed'
  const isFailed = project.status === 'failed'

  return (
    <div className="pda-layout">
      {/* 面包屑 */}
      <div className="pda-breadcrumb">
        <Breadcrumb
          items={[
            { label: '工作台' },
            { label: '混剪项目', icon: 'layers', onClick: () => navigate('/mix') },
            { label: project.name, icon: 'film' },
          ]}
        />
      </div>

      {/* 顶部信息 */}
      <div className="pda-header">
        {/* 缩略图 / 视频封面 */}
        <div className="pda-cover">
          {isCompleted ? (
            <div className="mix-cover-completed">
              <Icon name="layers" size={48} />
            </div>
          ) : (
            <div className={`pda-cover-placeholder`}>
              <div className="pda-cover-icon">
                <Icon name={project.status === 'failed' ? 'alert' : project.status === 'processing' ? 'clock' : 'layers'} size={48} />
              </div>
            </div>
          )}
        </div>

        <div className="pda-info">
          <div className="pda-info-top">
            <span className="status-pill" data-status={project.status}>
              {statusLabel[project.status] || project.status}
            </span>
            <span className="mix-tag" title="混剪项目">混剪</span>
            <span className="mix-tag-dim" title="目标时长">
              <Icon name="clock" size={11} /> 目标 {project.target_duration_seconds}s
            </span>
          </div>
          <h1 className="pda-title">{project.name}</h1>
          <div className="pda-meta">
            <span><Icon name="clock" size={11} /> {formatDate(project.created_at)}</span>
            {isCompleted && (
              <>
                <span className="pda-meta-sep">·</span>
                <span><Icon name="film" size={11} /> {formatTC(project.video_duration)}</span>
                <span className="pda-meta-sep">·</span>
                <span><Icon name="folder" size={11} /> {(project.video_size / 1024 / 1024).toFixed(1)} MB</span>
              </>
            )}
            <span className="pda-meta-sep">·</span>
            <span title="来源片段数">
              <Icon name="layers" size={11} /> {source_clips.length} 段
            </span>
          </div>
          <div className="pda-actions">
            {isCompleted && (
              <button className="btn btn-primary btn-sm">
                <Icon name="play" size={11} /> 播放预览
              </button>
            )}
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/mix/new')}>
              <Icon name="plus" size={11} /> 新建一个
            </button>
            <button className="btn btn-ghost btn-sm btn-danger" onClick={deleteProject}>
              <Icon name="trash" size={11} /> 删除
            </button>
          </div>
        </div>
      </div>

      {/* 处理中显示进度卡 */}
      {(project.status === 'processing' || project.status === 'pending') && task && (
        <div className="project-progress-card">
          <div className="project-progress-head">
            <Icon name="spinner" size={14} />
            <span>{task.current_step || '准备中...'}</span>
            <span className="project-progress-pct">{task.progress || 0}%</span>
          </div>
          <div className="project-progress-bar">
            <div className="project-progress-bar-fill" style={{ width: `${task.progress || 0}%` }} />
          </div>
        </div>
      )}

      {/* 失败显示错误 */}
      {isFailed && task?.error_message && (
        <div className="project-error-card">
          <div className="project-error-head">
            <Icon name="alert" size={14} /> 处理失败
          </div>
          <div className="project-error-body">{task.error_message}</div>
        </div>
      )}

      {/* 视频播放器 */}
      {isCompleted && (
        <div className="mix-player-card">
          <video
            className="mix-player-video"
            src={`/api/v1/mix/videos/${id}`}
            controls
            preload="metadata"
          />
        </div>
      )}

      {/* 主体: 脚本 + 来源片段表 */}
      <div className="mix-body">
        {/* 脚本预览 */}
        <div className="mix-script-card">
          <div className="mix-section-header">
            <Icon name="edit" size={13} />
            <span>脚本原文（将作为字幕烧录）</span>
          </div>
          <div className="mix-script-body">
            {project.script_text || '(无)'}
          </div>
        </div>

        {/* 来源片段表 */}
        <div className="mix-sources-card">
          <div className="mix-section-header">
            <Icon name="layers" size={13} />
            <span>来源片段（{source_clips.length} 段）</span>
          </div>
          {source_clips.length === 0 ? (
            <div className="mix-empty">暂无匹配的来源片段</div>
          ) : (
            <div className="mix-sources-table">
              <div className="mix-sources-row mix-sources-head">
                <div>#</div>
                <div>片段标题</div>
                <div>脚本片段</div>
                <div>匹配分</div>
                <div>时长</div>
              </div>
              {source_clips.map((sc) => (
                <div key={sc.id} className="mix-sources-row">
                  <div className="mix-sources-pos">{sc.position + 1}</div>
                  <div className="mix-sources-title" title={sc.source_project_name}>
                    <div className="mix-sources-title-main">{sc.source_clip_title || '(未命名)'}</div>
                    <div className="mix-sources-title-sub">{sc.source_project_name}</div>
                  </div>
                  <div className="mix-sources-text">{sc.script_segment_text || '(无)'}</div>
                  <div className="mix-sources-score">
                    <div className="mix-sources-score-bar">
                      <div
                        className="mix-sources-score-fill"
                        style={{ width: `${(sc.match_score || 0) * 100}%` }}
                      />
                    </div>
                    <span>{((sc.match_score || 0) * 100).toFixed(0)}%</span>
                  </div>
                  <div className="mix-sources-dur">{formatTC(sc.duration)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}