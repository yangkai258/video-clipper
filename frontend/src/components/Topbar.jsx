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
}) {
  const navigate = useNavigate()
  const location = useLocation()

  const pageTitle = location.pathname.startsWith('/project/')
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
          {location.pathname.startsWith('/project/') ? (
            <>
              <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)}>
                <Icon name="chevronLeft" size={12} />
              </button>
              <span className="breadcrumb-sep">/</span>
              <span className="page-title">项目详情</span>
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
