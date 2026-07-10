import { useLocation, useNavigate } from 'react-router-dom'
import Icon from '../Icon'
import ThemeToggle from '../ThemeToggle'
import UploadProgressBar from './UploadProgressBar'

// ponytail: Topbar 含面包屑 + 搜索 + 主题切换 + 上传按钮 + 进度条
// 12 个 props 全部传进来 (App 持有全部状态)
export default function Topbar({
  showTrash,
  showWatchFolders,
  search,
  setSearch,
  uploading,
  uploadState,
  uploadProgress,
  uploadError,
  handleUpload,
  handlePause,
  handleResume,
  handleCancel,
  versionLabel,
  isBeta,
  currentProjectName,
}) {
  const navigate = useNavigate()
  const location = useLocation()

  const isProjectDetail = location.pathname.startsWith('/project/')
  const pageTitle = isProjectDetail
    ? '项目详情'
    : location.pathname === '/styles'
      ? '风格管理'
      : showWatchFolders
        ? '监控文件夹'
        : showTrash
          ? '回收站'
          : '切片项目'

  return (
    <div className="topbar">
      <div className="topbar-left">
        <span className="breadcrumb">
          {isProjectDetail ? (
            // v2.2.4: 详情页面包屑 = "工作台 / 切片项目 / 项目名"
            // currentProjectName 从 App.jsx 的 projects list 缓存拿, 不走网络
            <>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => navigate('/')}
                title="返回项目列表"
              >
                <Icon name="chevronLeft" size={12} />
              </button>
              <span className="breadcrumb-sep">/</span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => navigate('/')}
                style={{ padding: '0 4px' }}
              >
                切片项目
              </button>
              <span className="breadcrumb-sep">/</span>
              <span className="page-title" title={currentProjectName || pageTitle}>
                {currentProjectName || pageTitle}
              </span>
            </>
          ) : (
            <>
              <span>工作台</span>
              <span className="breadcrumb-sep">/</span>
              <span className="page-title">{pageTitle}</span>
            </>
          )}
        </span>
      </div>
      <div className="topbar-right">
        <input
          className="search-input"
          type="text"
          placeholder="搜索项目..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <ThemeToggle />
        {versionLabel && (
          <span className={"version-badge " + (isBeta ? "version-beta" : "version-release")} title={versionLabel}>
            {versionLabel}
          </span>
        )}
        <label className="btn btn-primary upload-compact">
          {/* v2.1.35: SVG 替换 unicode, 玻璃按钮上的 emoji 看着糙 */}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          <span>新建切片</span>
          <input type="file" accept="video/*" onChange={handleUpload} disabled={uploading} />
        </label>
        {uploading && (
          <UploadProgressBar
            state={uploadState}
            progress={uploadProgress}
            error={uploadError}
            onPause={handlePause}
            onResume={handleResume}
            onCancel={handleCancel}
          />
        )}
      </div>
    </div>
  )
}
