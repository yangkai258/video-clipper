import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

import { useProjectData } from '../hooks/useProjectData'
import { useUrlTabs } from '../hooks/useUrlTabs'
import { useStatusNotifier } from '../hooks/useStatusNotifier'
import { API_BASE, statusLabel, formatTC, formatDate } from '../projectView'

import Icon from '../Icon'
import EmptyState from '../components/EmptyState'
import Breadcrumb from '../components/Breadcrumb'
import ProjectHeader from '../components/ProjectHeader'
import ProjectMetrics from '../components/ProjectMetrics'
import ProjectProgressCard from '../components/ProjectProgressCard'
import ProjectErrorCard from '../components/ProjectErrorCard'
import ProjectSidebar from '../components/ProjectSidebar'
import ClipsTab from '../components/ClipsTab'
import CollectionsTab from '../components/CollectionsTab'
import SrtTab from '../components/SrtTab'
import SettingsTab from '../components/SettingsTab'
import ReportModal from '../components/ReportModal'

// ponytail: 主组件仅负责装配 — 状态与业务逻辑都抽到 hooks / sub-components
export default function ProjectDetail({ projectId, navigate: navProp }) {
  // 必须在所有 state 之前无条件 hook,避免 hooks 顺序违规
  const _navHook = useNavigate()
  const navigate = navProp || _navHook
  const id = projectId
  const [showReport, setShowReport] = useState(false)
  const [_showRerun, setShowRerun] = useState(false)

  // ponytail: 必须在所有 hook 之前且无条件执行,避免 hooks 顺序违规
  useEffect(() => {
    if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
  }, [])

  const { project, loading, reload } = useProjectData(id)
  useStatusNotifier(project)

  const { activeTab, setActiveTab, clipsPage, setClipsPage, collectionsPage, setCollectionsPage } = useUrlTabs()

  const startProcessing = async () => {
    try {
      await axios.post(`${API_BASE}/projects/${id}/process`)
      reload()
    } catch (e) {
      alert('启动失败：' + (e.response?.data?.detail || e.message))
    }
  }

  const deleteProject = async () => {
    if (!confirm(`确定删除「${project?.name}」？此操作不可恢复。`)) return
    try {
      await axios.delete(`${API_BASE}/projects/${id}`)
      navigate('/')
    } catch (e) {
      alert('删除失败：' + e.message)
    }
  }

  // v2.2.5: 一键把整个项目所有 clip 批量导入资源库 (放在 useMemo 前, 避免 TDZ)
  const handleSaveAllToLibrary = async () => {
    if (!project || project.status !== 'completed') return
    if (!confirm(`把项目「${project.name}」的全部 ${project.clips?.length || 0} 个片段批量存入资源库？`)) return
    try {
      const r = await axios.post(`${API_BASE}/library/from-project`, {
        source_project_id: project.id,
      })
      const imported = r.data.imported ?? 0
      const skipped = r.data.skipped ?? 0
      const errors = r.data.errors?.length ?? 0
      alert(`批量导入完成:\n• 新增 ${imported} 个\n• 已存在跳过 ${skipped}\n• 失败 ${errors} 个\n去「资源库」页面查看`)
      reload()
    } catch (err) {
      alert('批量导入失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  // 被重复读取的派生数据在这里一次性算好
  const view = useMemo(() => {
    if (!project) return null
    const clips = project.clips || []
    const collections = project.collections || []
    const task = project.task
    const cfg = project.processing_config || {}
    const avgDuration = clips.length > 0 ? clips.reduce((a, c) => a + (c.duration || 0), 0) / clips.length : 0
    const avgScore = clips.length > 0 ? clips.reduce((a, c) => a + (c.score || 0), 0) / clips.length : 0
    const elapsed = (task?.started_at && (task?.completed_at || task?.failed_at))
      ? (new Date(task.completed_at || task.failed_at) - new Date(task.started_at)) / 1000
      : null
    const elapsedStr = elapsed ? `${Math.round(elapsed / 60)} 分钟` : '—'
    return {
      clips, collections, task, cfg,
      avgDuration, avgScore, elapsedStr,
      isProcessing: project.status === 'processing',
      subtitlePath: project.subtitle_path,
      headerProps: {
        project: {
          ...project,
          statusLabel: statusLabel[project.status] || project.status,
          formattedDuration: formatTC(project.video_duration),
          formattedSize: project.video_size ? `${(project.video_size / 1024 / 1024).toFixed(1)} MB` : '—',
          formattedCreatedAt: formatDate(project.created_at),
        },
        onStart: startProcessing,
        onShowReport: () => setShowReport(true),
        onDelete: deleteProject,
        onRerun: () => setShowRerun(true),  // v2.2.1: 重新处理
        onSaveAllToLibrary: handleSaveAllToLibrary,  // v2.2.5: 一键存全部
      },
    }
  }, [project])

  if (loading) {
    return <EmptyState icon={<Icon name="clock" size={32} />} title="加载中..." />
  }
  if (!project) {
    return (
      <EmptyState
        icon={'∅'}
        title="项目不存在"
        hint="它可能已被删除"
        action={<button className="btn btn-primary" style={{ marginTop: 'var(--space-3)' }} onClick={() => navigate('/')}>返回列表</button>}
      />
    )
  }

  const { clips, collections, task, cfg, isProcessing, headerProps } = view
  const showTabs = clips.length > 0 || collections.length > 0
  const currentPage = activeTab === 'collections' ? collectionsPage : clipsPage
  const setCurrentPage = activeTab === 'collections' ? setCollectionsPage : setClipsPage

  // v2.2.5: 存入资源库 handler — 透传到 ClipCard
  const handleSaveToLibrary = async ({ source_project_id, source_clip_id }) => {
    try {
      const r = await axios.post(`${API_BASE}/library/from-clip`, {
        source_project_id,
        source_clip_id,
      })
      alert(`已存入资源库: ${r.data.name || ''}`)
      // 刷新当前项目 (clip 仍在, 不需要 reload, 仅提示)
    } catch (err) {
      alert('存入资源库失败: ' + (err.response?.data?.detail || err.message))
      throw err  // 让 ClipCard 重置 saving 状态
    }
  }

  return (
    <div className="pda-layout">
      {/* v2.2.4: 面包屑 — 工作台 / 切片项目 / 当前项目 */}
      <div className="pda-breadcrumb">
        <Breadcrumb
          items={[
            { label: '工作台' },
            { label: '切片项目', icon: 'list', onClick: () => navigate('/') },
            { label: project.name, icon: 'film' },
          ]}
        />
      </div>
      <ProjectHeader {...headerProps} />
      <ProjectMetrics
        clipsCount={clips.length}
        collectionsCount={collections.length}
        avgDuration={view.avgDuration}
        avgScore={view.avgScore}
      />
      {isProcessing && <ProjectProgressCard task={task} />}
      {project.status === 'failed' && task?.error_message && (
        <ProjectErrorCard errorMessage={task.error_message} onRetry={startProcessing} />
      )}

      <div className="pda-body">
        <div className="pda-main">
          {showTabs ? (
            <>
              <div className="pda-tabs">
                {clips.length > 0 && (
                  <button className={`pda-tab ${activeTab === 'clips' ? 'active' : ''}`} onClick={() => setActiveTab('clips')}>
                    切片 <span className="pda-tab-count">{clips.length}</span>
                  </button>
                )}
                {collections.length > 0 && (
                  <button className={`pda-tab ${activeTab === 'collections' ? 'active' : ''}`} onClick={() => setActiveTab('collections')}>
                    合集 <span className="pda-tab-count">{collections.length}</span>
                  </button>
                )}
                <button className={`pda-tab ${activeTab === 'srt' ? 'active' : ''}`} onClick={() => setActiveTab('srt')}>字幕</button>
                <button className={`pda-tab ${activeTab === 'settings' ? 'active' : ''}`} onClick={() => setActiveTab('settings')}>设置</button>
              </div>

              {activeTab === 'clips' && <ClipsTab projectId={id} clips={clips} withSubtitle={cfg.with_subtitle !== false} currentPage={currentPage} onPageChange={setCurrentPage} onSaveToLibrary={handleSaveToLibrary} />}
              {activeTab === 'collections' && <CollectionsTab projectId={id} collections={collections} />}
              {activeTab === 'srt' && <SrtTab projectId={id} subtitlePath={view.subtitlePath} />}
              {activeTab === 'settings' && <SettingsTab project={project} cfg={cfg} />}
            </>
          ) : (
            <EmptyState
              icon={isProcessing ? <Icon name="clock" size={32} /> : project.status === 'failed' ? <Icon name="x" size={32} /> : <Icon name="film" size={32} />}
              title={isProcessing ? '处理中，请稍候...' : project.status === 'pending' ? '项目就绪' : project.status === 'failed' ? '处理失败' : '暂无视频数据'}
              hint={project.status === 'pending' ? '点击顶部「开始处理」生成切片' : project.status === 'failed' ? '请检查日志或重新处理' : null}
            />
          )}
        </div>

        <ProjectSidebar project={project} task={task} cfg={cfg} elapsedStr={view.elapsedStr} />
      </div>

      {showReport && <ReportModal project={project} onClose={() => setShowReport(false)} />}
    </div>
  )
}
