import { useLocation, useNavigate } from 'react-router-dom'
import Icon from '../Icon'  // eslint-disable-line no-unused-vars

// ponytail: Sidebar 5 nav buttons + brand + user chip
// v2.2.4: 加"混剪项目"入口
// v2.2.5: 加"资源库"入口
// v2.2.6: 加"批量混剪"入口 (混剪项目下面子菜单)
export default function Sidebar({
  showTrash,
  showWatchFolders,
  onProjects,
  onTrash,
  onStyles,
  onWatchFolders,
  onMix,
  onMixBatch,
  onLibrary,
}) {
  const _navigate = useNavigate()
  const location = useLocation()

  const isProjectsActive = (location.pathname === '/' || location.pathname.startsWith('/project/')) && !showTrash && !showWatchFolders
  const isMixActive = location.pathname === '/mix' && !showTrash && !showWatchFolders
  const isMixBatchActive = location.pathname.startsWith('/mix/batch') && !showTrash && !showWatchFolders
  const isTrashActive = showTrash
  const isStylesActive = location.pathname === '/styles' && !showTrash && !showWatchFolders
  const isWatchActive = showWatchFolders
  const isLibraryActive = location.pathname.startsWith('/library') && !showTrash && !showWatchFolders

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark">VC</div>
        <div className="sidebar-brand-name">视频切片工具</div>
      </div>

      <button
        className={`nav-item ${isProjectsActive ? 'active' : ''}`}
        onClick={onProjects}
      >
        <span className="nav-item-icon"><Icon name="scissors" /></span>
        切片项目
      </button>
      {/* v2.2.4: 混剪项目入口 (跟切片独立) */}
      <button
        className={`nav-item ${isMixActive ? 'active' : ''}`}
        onClick={onMix}
      >
        <span className="nav-item-icon"><Icon name="layers" /></span>
        混剪项目
      </button>
      {/* v2.2.6: 批量混剪入口 (混剪的批量提交, 一次跑多个变体) */}
      <button
        className={`nav-item nav-item-child ${isMixBatchActive ? 'active' : ''}`}
        onClick={onMixBatch}
        style={{ paddingLeft: 28, fontSize: 13 }}
      >
        <span className="nav-item-icon"><Icon name="layers" size={12} /></span>
        批量混剪
      </button>
      <button
        className={`nav-item ${isTrashActive ? 'active' : ''}`}
        onClick={onTrash}
      >
        <span className="nav-item-icon"><Icon name="trash" /></span>
        回收站
      </button>
      <button
        className={`nav-item ${isStylesActive ? 'active' : ''}`}
        onClick={onStyles}
      >
        <span className="nav-item-icon"><Icon name="edit" /></span>
        风格管理
      </button>
      <button
        className={`nav-item ${isLibraryActive ? 'active' : ''}`}
        onClick={onLibrary}
      >
        <span className="nav-item-icon"><Icon name="database" /></span>
        资源库
      </button>
      <button
        className={`nav-item ${isWatchActive ? 'active' : ''}`}
        onClick={onWatchFolders}
      >
        <span className="nav-item-icon"><Icon name="folder" /></span>
        监控文件夹
      </button>

      <div className="sidebar-bottom">
        <div className="user-chip">
          <div className="user-avatar">U</div>
          <div>
            <div className="user-name">工作台</div>
            <div className="user-status">● 在线</div>
          </div>
        </div>
      </div>
    </aside>
  )
}