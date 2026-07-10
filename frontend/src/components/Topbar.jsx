import { useLocation, useNavigate } from 'react-router-dom'
import Icon from '../Icon'
import ThemeToggle from '../ThemeToggle'
import UploadProgressBar from './UploadProgressBar'

// ponytail: Topbar 含面包屑 + 搜索 + 主题切换 + 上传进度条
// v2.2.5: "新建切片" 按钮从 Topbar 挪到内容区 content-header (跟混剪一致)
//         Topbar 只剩上传进度条 (uploading 时显示), 不再有"新建切片"按钮
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
  const isMixDetail = location.pathname.startsWith('/mix/') && !location.pathname.startsWith('/mix/new')
  const isMixWizard = location.pathname === '/mix/new'
  const isMixList = location.pathname === '/mix' || isMixDetail || isMixWizard
  const isLibrary = location.pathname.startsWith('/library')
  const pageTitle = isProjectDetail
    ? '项目详情'
    : isMixDetail
      ? '混剪详情'
      : isMixWizard
        ? '新建混剪'
        : location.pathname === '/styles'
          ? '风格管理'
          : location.pathname === '/mix'
            ? '混剪项目'
            : isLibrary
              ? '资源库'
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
          ) : isMixList ? (
            // v2.2.4: 混剪页面包屑 = "工作台 / 混剪项目 / [wizard|detail]"
            <>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => navigate('/mix')}
                title="返回混剪列表"
              >
                <Icon name="chevronLeft" size={12} />
              </button>
              <span className="breadcrumb-sep">/</span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => navigate('/mix')}
                style={{ padding: '0 4px' }}
              >
                混剪项目
              </button>
              {(isMixDetail || isMixWizard) && (
                <>
                  <span className="breadcrumb-sep">/</span>
                  <span className="page-title">{pageTitle}</span>
                </>
              )}
            </>
          ) : isLibrary ? (
            // v2.2.5: 资源库面包屑 = "工作台 / 资源库"
            <>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => navigate('/library')}
                title="资源库"
              >
                <Icon name="chevronLeft" size={12} />
              </button>
              <span className="breadcrumb-sep">/</span>
              <span className="page-title">{pageTitle}</span>
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
        {/* v2.2.5: "新建切片" 按钮挪到内容区 content-header (跟混剪风格一致) */}
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
