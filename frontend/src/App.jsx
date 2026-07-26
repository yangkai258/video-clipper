import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation, useParams } from 'react-router-dom'
import axios from 'axios'

const API_BASE = '/api/v1'
import { ChunkedUploader, formatBytes, formatSpeed, formatTime } from './ChunkedUploader'
import WatchFolders from './pages/WatchFolders'
import StyleManager from './pages/StyleManager'
import ProjectDetail from './pages/ProjectDetail'
import ThemeToggle from './ThemeToggle'
import UploadProgressBar from './components/UploadProgressBar'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import { useProjects } from './hooks/useProjects'
import { useUpload } from './hooks/useUpload'
import { useStrategy } from './hooks/useStrategy'
import Icon from './Icon'
import { formatDuration, formatTC, formatDate, statusLabel } from './projectView'
import ProjectCard from './components/ProjectCard'
import StrategyModal from './components/StrategyModal'
import TrashView from './components/TrashView'
// v2.2.4: 混剪独立路由页面
import MixListPage from './pages/MixListPage'
import MixWizardPage from './pages/MixWizardPage'
import MixDetailPage from './pages/MixDetailPage'
// v2.2.6: 批量混剪路由页面
import MixBatchListPage from './pages/MixBatchListPage'
import MixBatchWizardPage from './pages/MixBatchWizardPage'
import MixBatchDetailPage from './pages/MixBatchDetailPage'
// v2.2.5: 资源库独立路由页面
import LibraryPage from './pages/LibraryPage'
// v2.2.30: ErrorBoundary 兜底 — 任一子组件崩了显示"刷新重试", 不让 Topbar 全挂
import { ErrorBoundary } from './ErrorBoundary'
import './index.css'

function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const [showWatchFolders, setShowWatchFolders] = useState(false)
  const [pendingProject, setPendingProject] = useState(null)  // strategy modal target

  // 3 hooks split out projects/upload/strategy logic (see hooks/*.js)
  const projectsApi = useProjects()
  const { projects, setProjects, trashProjects, showTrash, setShowTrash, activeTab, setActiveTab, search, setSearch, filteredProjects, counts, loadProjects, loadTrash, deleteProject, restoreProject, purgeTrash, purgeAllTrash } = projectsApi
  const strategyApi = useStrategy({ onAfterProcess: loadProjects })
  const { showStrategyModal, setShowStrategyModal, presets, customStyles, withSubtitle, setWithSubtitle, outputFormat, setOutputFormat, loadStrategies, openStrategyModal, closeStrategyModal, selectStrategy, startProcessing } = strategyApi
  const uploadApi = useUpload({
    onDone: ({ projectId, name }) => {
      setPendingProject({ id: projectId, name })
      openStrategyModal()
      loadProjects()
    },
  })
  const { uploading, uploadProgress, uploadState, uploadError, handleUpload, handlePause, handleResume, handleCancel } = uploadApi

  // v2.2.4: 当前项目名 (Topbar 面包屑用) — 从 projects list 缓存拿, 无网络请求
  const { id: routeProjectId } = useParams()
  const currentProjectName = routeProjectId
    ? projects.find(p => p.id === routeProjectId)?.name || ''
    : ''

  // v2.2.40: 列表卡片"存到资源库" — 调 POST /library/from-project 批量加
  // (跟 ProjectDetail 页面的"批量存"是同一个 endpoint)
  const saveProjectToLibrary = async (project) => {
    if (!project || !project.id) return
    if (!confirm(`把项目「${project.name}」的全部 ${project.clip_count || 0} 个切片批量存入资源库？`)) return
    try {
      const r = await axios.post(`${API_BASE}/library/from-project`, {
        source_project_id: project.id,
      })
      alert(`批量导入完成:\n• 新增 ${r.data.imported} 个\n• 已存在跳过 ${r.data.skipped} 个\n• 失败 ${r.data.errors?.length || 0} 个\n去「资源库」页面查看`)
    } catch (err) {
      alert('批量导入失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  useEffect(() => {
    loadProjects()
    loadStrategies()
  }, [loadProjects, loadStrategies])

  const isBeta = window.location.port === '3030'
  const VERSION_LABEL = `${isBeta ? '测试版' : '正式版'} ${typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev'}`
  const VERSION_CLASS = isBeta ? 'version-beta' : 'version-release'

  return (
    <div className="app-shell">
      <Sidebar
        showTrash={showTrash}
        showWatchFolders={showWatchFolders}
        onProjects={() => { setShowTrash(false); setShowWatchFolders(false); navigate('/') }}
        onTrash={() => { navigate('/'); setShowTrash(true); setShowWatchFolders(false); loadTrash() }}
        onStyles={() => { navigate('/styles'); setShowTrash(false); setShowWatchFolders(false) }}
        onWatchFolders={() => { navigate('/'); setShowWatchFolders(true); setShowTrash(false) }}
        onMix={() => { setShowTrash(false); setShowWatchFolders(false); navigate('/mix') }}
        onMixBatch={() => { setShowTrash(false); setShowWatchFolders(false); navigate('/mix/batch') }}
        onLibrary={() => { setShowTrash(false); setShowWatchFolders(false); navigate('/library') }}
      />

      <main className="main">
        <Topbar
          showTrash={showTrash}
          showWatchFolders={showWatchFolders}
          search={search}
          setSearch={setSearch}
          uploading={uploading}
          uploadState={uploadState}
          uploadProgress={uploadProgress}
          uploadError={uploadError}
          handleUpload={handleUpload}
          handlePause={handlePause}
          handleResume={handleResume}
          handleCancel={handleCancel}
          versionLabel={VERSION_LABEL}
          isBeta={isBeta}
          currentProjectName={currentProjectName}
        />

        <div className="content fade-in">
          {/* 路径优先分发: 批量混剪详情/向导/列表 → 资源库 / 混剪详情 / 混剪向导 / 项目详情 / 风格管理 / 监控 / 回收站 / 主列表 / 混剪列表 */}
          {location.pathname === '/library' ? (
            <LibraryPage />
          ) : location.pathname.startsWith('/mix/batch/') && !location.pathname.startsWith('/mix/batch/new') ? (
            <MixBatchDetailInShell />
          ) : location.pathname === '/mix/batch/new' ? (
            <MixBatchWizardPage navigate={navigate} />
          ) : location.pathname === '/mix/batch' ? (
            <MixBatchListPage navigate={navigate} />
          ) : location.pathname.startsWith('/mix/') && !location.pathname.startsWith('/mix/new') ? (
            <MixDetailInShell />
          ) : location.pathname === '/mix/new' ? (
            <MixWizardPage navigate={navigate} />
          ) : location.pathname === '/mix' ? (
            <MixListPage navigate={navigate} />
          ) : location.pathname.startsWith('/project/') ? (
            <ProjectDetailInShell />
          ) : location.pathname === '/styles' ? (
            <StyleManager navigate={navigate} location={location} />
          ) : showWatchFolders ? (
            <ErrorBoundary><WatchFolders /></ErrorBoundary>
          ) : showTrash ? (
          <ErrorBoundary>
            <TrashView
              trashProjects={trashProjects}
              onPurgeAll={purgeAllTrash}
              onPurgeOld={purgeTrash}
              onRestore={restoreProject}
              onPermanentDelete={(id, name) => deleteProject(id, name, true)}
            />
          </ErrorBoundary>
          ) : (
            // === 正常项目列表 ===
            <>
              {/* v2.1.11: Hero 行 — 信息卡 + metric (按钮在 topbar) */}
              <div className="hero-row">
                <div className="hero-card">
                  <div className="hero-card-icon"><Icon name="film" size={20} /></div>
                  <div className="hero-card-body">
                    <div className="hero-card-title">
                      {uploading ? `上传中 ${uploadProgress}%` : '视频切片 AI'}
                    </div>
                    <div className="hero-card-sub">
                      {uploading
                        ? `${formatBytes(uploadProgress.received)} / ${formatBytes(uploadProgress.total)}`
                        : '点右上角 "+ 新建切片" 上传视频，AI 自动生成金句片段'}
                    </div>
                  </div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">项目数</div>
                  <div className="metric-value">{projects.length}</div>
                  <div className="metric-sub">{counts.completed} 已完成</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">成功率</div>
                  <div className="metric-value">
                    {projects.length > 0
                      ? Math.round((counts.completed / (counts.completed + counts.failed || 1)) * 100)
                      : 0}%
                  </div>
                  <div className="metric-sub">{counts.failed} 失败</div>
                </div>
              </div>

              {/* v2.2.5: 新建切片从 Topbar 挪到内容区 (跟混剪一致) */}
              <div className="content-header">
                <div className="content-header-left">
                  {/* 列表 tab 后续渲染, 这里只放搜索框/占位 */}
                </div>
                <div className="content-header-right">
                  <label className="btn btn-primary">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                      <path d="M12 5v14M5 12h14" />
                    </svg>
                    <span>新建切片</span>
                    <input
                      type="file"
                      accept="video/*"
                      onChange={handleUpload}
                      disabled={uploading}
                      style={{ display: 'none' }}
                    />
                  </label>
                </div>
              </div>

              <div className="tabs">
                {[
                  ['all', '全部'],
                  ['processing', '处理中'],
                  ['completed', '已完成'],
                  ['pending', '待处理'],
                  ['failed', '失败'],
                ].map(([k, label]) => (
                  <button
                    key={k}
                    className={`tab ${activeTab === k ? 'active' : ''}`}
                    onClick={() => setActiveTab(k)}
                  >
                    {label}
                    <span className="tab-count">{counts[k]}</span>
                  </button>
                ))}
              </div>

              {filteredProjects.length > 0 ? (
                <ErrorBoundary>
                  <div className="reel-grid">
                    {filteredProjects.map(p => (
                      <ProjectCard
                        key={p.id}
                        project={p}
                        onStart={startProcessing}
                        onDelete={deleteProject}
                        onSaveToLibrary={saveProjectToLibrary}  /* v2.2.40: 列表卡片快捷存到资源库 */
                      />
                    ))}
                  </div>
                </ErrorBoundary>
              ) : (
                <div className="empty">
                  <div className="empty-icon">∅</div>
                  <div className="empty-title">还没有切片项目</div>
                  <div className="empty-hint">
                    点击右上角 <b style={{ color: 'var(--accent)' }}><Icon name="plus" size={11} style={{ verticalAlign: '-2px', marginRight: 2 }} />新建切片</b> 上传第一个视频
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </main>

      {showStrategyModal && (
        <StrategyModal
          pendingProject={pendingProject}
          setPendingProject={setPendingProject}
          presets={presets}
          customStyles={customStyles}
          withSubtitle={withSubtitle}
          setWithSubtitle={setWithSubtitle}
          outputFormat={outputFormat}
          setOutputFormat={setOutputFormat}
          onSelect={(s) => selectStrategy(s, pendingProject)}
          onClose={closeStrategyModal}
        />
      )}
    </div>
  )
}

// v2.1.32: ProjectDetailInShell 提到模块顶层 (不再嵌在 App 内部)
// 原因: 嵌在 App 内部时, 每次 App re-render 它都是新的 function reference,
//       React unmount + remount 整个 ProjectDetail → 每 5s 一次 '加载中...' 闪烁
// 注: useNavigate() 必须在 router context 内, 模块顶层函数能正常用因为它在 <Routes> 内部被渲染
function ProjectDetailInShell() {
  const { id } = useParams()
  const navigate = useNavigate()
  return <ProjectDetail projectId={id} navigate={navigate} />
}

// v2.2.4: MixDetailInShell 同样模块顶层 (防 HMR state slot 错位)
function MixDetailInShell() {
  const { id } = useParams()
  const navigate = useNavigate()
  return <MixDetailPage projectId={id} navigate={navigate} />
}

// v2.2.6: MixBatchDetailInShell 模块顶层
function MixBatchDetailInShell() {
  const { id } = useParams()
  const navigate = useNavigate()
  return <MixBatchDetailPage batchId={id} navigate={navigate} />
}


export default App