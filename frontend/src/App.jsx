import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation, useParams } from 'react-router-dom'
import axios from 'axios'
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
          {/* 路径优先分发: 混剪详情 / 混剪向导 / 项目详情 / 风格管理 / 监控 / 回收站 / 主列表 / 混剪列表 */}
          {location.pathname.startsWith('/mix/') && !location.pathname.startsWith('/mix/new') ? (
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
            <WatchFolders />
          ) : showTrash ? (
          <TrashView
            trashProjects={trashProjects}
            onPurgeAll={purgeAllTrash}
            onPurgeOld={purgeTrash}
            onRestore={restoreProject}
            onPermanentDelete={(id, name) => deleteProject(id, name, true)}
          />
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
                <div className="reel-grid">
                  {filteredProjects.map(p => (
                    <ProjectCard
                      key={p.id}
                      project={p}
                      onStart={startProcessing}
                      onDelete={deleteProject}
                    />
                  ))}
                </div>
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


export default App